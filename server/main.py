#!/usr/bin/env python3
"""
AUBus – Server (Phase 0 + P1-05, no tokens)
-------------------------------------------
TCP + JSON Lines, one connection per client.
Protocol:
  - Envelope: {type, id (uuid4), payload?}
  - After AUTH.LOGIN_RES, we bind this connection to user_id and use it for later messages.
Supported:
  CONTROL: PING -> PONG
  AUTH:    REGISTER_REQ/RES, LOGIN_REQ/RES, LOGOUT_REQ/RES
  PROFILE: SET_REQ/RES, GET_REQ/RES
"""

import argparse
import json
import logging
import socket
import threading
import traceback
import uuid
import sqlite3
import re

ENCODING = "utf-8"
BACKLOG = 64
RECV_BUFSIZE = 4096
DB_PATH = "database.db"

# ---------- Envelope / validation ----------

def is_valid_uuid4(value: str) -> bool:
    if not isinstance(value, str):
        return False
    try:
        u = uuid.UUID(value, version=4)
    except (ValueError, TypeError):
        return False
    # accept exact or case-variants of canonical str
    return str(u) in (value, value.lower(), value.upper())

def bad_request(mid, message):
    return {"type": "ERROR", "id": mid, "payload": {"code": "BAD_REQUEST", "message": message}}

def forbidden(mid, message):
    return {"type": "ERROR", "id": mid, "payload": {"code": "FORBIDDEN", "message": message}}

def not_found(mid, message):
    return {"type": "ERROR", "id": mid, "payload": {"code": "NOT_FOUND", "message": message}}

def server_error(mid, message="Internal error"):
    return {"type": "ERROR", "id": mid, "payload": {"code": "SERVER_ERROR", "message": message}}

# ---------- JSON-L helpers ----------

def recv_lines(sock: socket.socket):
    buf = b""
    while True:
        chunk = sock.recv(RECV_BUFSIZE)
        if not chunk:
            return
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            yield line.decode(ENCODING, errors="replace").rstrip("\r").strip()

def send_json(sock: socket.socket, obj: dict):
    data = (json.dumps(obj, separators=(",", ":")) + "\n").encode(ENCODING)
    sock.sendall(data)

# ---------- AUTH: REGISTER / LOGIN ----------

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,20}$")
PASSWORD_RE = re.compile(r"^.{6,20}$")
EMAIL_RE    = re.compile(r"^[^@]+@[^@]+\.[^@]+$")

def validate_register_payload(p):
    missing = [k for k in ("name", "email", "username", "password", "area") if k not in p]
    if missing:
        return False, f"Missing fields: {', '.join(missing)}"
    if not USERNAME_RE.match(p["username"]):
        return False, "Invalid username (5-20 letters/digits/underscores)"
    if not PASSWORD_RE.match(p["password"]):
        return False, "Invalid password (6-20 characters)"
    if not EMAIL_RE.match(p["email"]):
        return False, "Invalid email format"
    if not isinstance(p["area"], str) or not p["area"]:
        return False, "Area must be a non-empty string"
    return True, ""

def db_connect():
    # Simple helper for clarity
    return sqlite3.connect(DB_PATH)

def auth_register(mid, payload):
    ok, msg = validate_register_payload(payload or {})
    if not ok:
        return bad_request(mid, msg)
    try:
        with db_connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO users (name, username, password, email, is_driver, area) "
                "VALUES (?, ?, ?, ?, 0, ?)",
                (payload["name"], payload["username"], payload["password"], payload["email"], payload["area"]),
            )
            user_id = cur.lastrowid
        return {"type": "AUTH.REGISTER_RES", "id": mid, "payload": {"user_id": f"user_{user_id}"}}
    except sqlite3.IntegrityError as e:
        err = str(e).lower()
        if "username" in err:
            return {"type": "ERROR", "id": mid, "payload": {"code": "AUTH_USERNAME_TAKEN", "message": "Username already exists"}}
        if "email" in err:
            return {"type": "ERROR", "id": mid, "payload": {"code": "AUTH_EMAIL_TAKEN", "message": "Email already exists"}}
        return server_error(mid, "Database error")
    except Exception:
        logging.exception("auth_register")
        return server_error(mid)

def row_to_user_preview(row):
    # row = (user_id,name,username,password,email,is_driver,area,rating_sum,rating_avg,rating_count)
    return {
        "user_id": f"user_{row[0]}",
        "username": row[2],
        "name": row[1],
        "area": row[6],
        "is_driver": bool(row[5]),
        "rating": float(row[8]) if row[8] is not None else 0.0,
    }

def auth_login(mid, payload, conn_state):
    p = payload or {}
    for k in ("username", "password"):
        if k not in p or not isinstance(p[k], str) or not p[k]:
            return bad_request(mid, f"Missing/invalid field: {k}")
    try:
        with db_connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT user_id,name,username,password,email,is_driver,area,rating_sum,rating_avg,rating_count "
                "FROM users WHERE username=?",
                (p["username"],),
            )
            row = cur.fetchone()
            if not row or row[3] != p["password"]:
                return {"type": "ERROR", "id": mid, "payload": {"code": "AUTH_INVALID_CREDENTIALS", "message": "Invalid username or password"}}
        # Bind this connection to user_id (no tokens)
        conn_state["user_id"] = int(row[0])
        return {"type": "AUTH.LOGIN_RES", "id": mid, "payload": {"user": row_to_user_preview(row)}}
    except Exception:
        logging.exception("auth_login")
        return server_error(mid)

def auth_logout(mid, conn_state):
    # Clear association and acknowledge
    conn_state["user_id"] = None
    return {"type": "AUTH.LOGOUT_RES", "id": mid, "payload": {"message": "Logout Successful"}}

# ---------- PROFILE: SET / GET (no tokens; requires logged-in conn) ----------

def profile_set(mid, payload, conn_state):
    user_id = conn_state.get("user_id")
    if not user_id:
        return forbidden(mid, "Login required")

    p = payload or {}
    # Protocol definition:
    # {
    #   "is_driver": <bool/int>,
    #   "vehicle": {"model":"","make":"","year":"","color":"","plate":""} (optional)
    #   "area": "<str>"
    # }
    is_driver = 1 if p.get("is_driver") else 0
    area = p.get("area")
    if not isinstance(area, str) or not area:
        return {"type": "ERROR", "id": mid, "payload": {"code": "PROFILE_AREA_REQUIRED", "message": "area is required"}}

    vehicle = p.get("vehicle") or {}
    v_make  = vehicle.get("make")
    v_model = vehicle.get("model")
    v_color = vehicle.get("color")
    v_plate = vehicle.get("plate")

    try:
        with db_connect() as conn:
            cur = conn.cursor()
            # Keep users table in sync
            cur.execute("UPDATE users SET is_driver=?, area=? WHERE user_id=?", (is_driver, area, user_id))

            # Upsert into profiles table
            cur.execute("SELECT user_id FROM profiles WHERE user_id=?", (user_id,))
            exists = cur.fetchone()
            if exists:
                cur.execute(
                    "UPDATE profiles SET is_driver=?, area=?, vehicle_make=?, vehicle_model=?, vehicle_color=?, vehicle_plate=? "
                    "WHERE user_id=?",
                    (is_driver, area, v_make, v_model, v_color, v_plate, user_id),
                )
            else:
                cur.execute(
                    "INSERT INTO profiles (user_id, is_driver, area, vehicle_make, vehicle_model, vehicle_color, vehicle_plate) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (user_id, is_driver, area, v_make, v_model, v_color, v_plate),
                )
        # Per your protocol, SET_RES returns empty payload
        return {"type": "PROFILE.SET_RES", "id": mid, "payload": {}}
    except Exception:
        logging.exception("profile_set")
        return server_error(mid, "Failed to update profile")

def profile_get(mid, payload, conn_state):
    p = payload or {}
    # If user_id provided: use it; else default to current connection user
    target_uid = None
    if "user_id" in p and isinstance(p["user_id"], str) and p["user_id"].startswith("user_"):
        try:
            target_uid = int(p["user_id"].split("_", 1)[1])
        except ValueError:
            return bad_request(mid, "Invalid user_id format")
    else:
        target_uid = conn_state.get("user_id")

    if not target_uid:
        return forbidden(mid, "Login required or provide user_id")

    try:
        with db_connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT user_id,name,username,password,email,is_driver,area,rating_sum,rating_avg,rating_count "
                "FROM users WHERE user_id=?",
                (target_uid,),
            )
            row = cur.fetchone()
            if not row:
                return not_found(mid, "User not found")
            user = {
                "user_id": f"user_{row[0]}",
                "name": row[1],
                "area": row[6],
                "is_driver": bool(row[5]),
                "rating": float(row[8]) if row[8] is not None else 0.0,
            }
        return {"type": "PROFILE.GET_RES", "id": mid, "payload": {"user": user}}
    except Exception:
        logging.exception("profile_get")
        return server_error(mid)

# ---------- Dispatcher ----------

def handle_message(msg: dict, conn_state: dict):
    # Validate envelope
    if "type" not in msg or "id" not in msg:
        return bad_request(msg.get("id"), "Missing required field(s): type, id")
    if not is_valid_uuid4(msg["id"]):
        return bad_request(msg["id"], "Field 'id' must be a valid UUIDv4 string")

    mtype = msg["type"]
    mid = msg["id"]
    payload = msg.get("payload")

    # CONTROL
    if mtype == "PING":
        return {"type": "PONG", "id": mid, "payload": {}}

    # AUTH
    if mtype == "AUTH.REGISTER_REQ":
        return auth_register(mid, payload)
    if mtype == "AUTH.LOGIN_REQ":
        return auth_login(mid, payload, conn_state)
    if mtype == "AUTH.LOGOUT_REQ":
        return auth_logout(mid, conn_state)

    # PROFILE
    if mtype == "PROFILE.SET_REQ":
        return profile_set(mid, payload, conn_state)
    if mtype == "PROFILE.GET_REQ":
        return profile_get(mid, payload, conn_state)

    # Unknown
    return {"type": "ERROR", "id": mid, "payload": {"code": "UNKNOWN_TYPE", "message": f"Unsupported type: {mtype}"}}

# ---------- Per-client thread & server ----------

def client_thread(conn: socket.socket, addr):
    peer = f"{addr[0]}:{addr[1]}"
    logging.info("Client connected: %s", peer)

    # connection-local state (no tokens, per your protocol)
    conn_state = {"user_id": None}

    try:
        for line in recv_lines(conn):
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                send_json(conn, {"type": "ERROR", "id": None, "payload": {"code": "BAD_JSON", "message": "Invalid JSON"}})
                continue
            try:
                resp = handle_message(msg, conn_state)
            except Exception:
                logging.error("Handler error:\n%s", traceback.format_exc())
                resp = server_error(msg.get("id"))
            send_json(conn, resp)
    except (ConnectionResetError, BrokenPipeError):
        logging.info("Client reset: %s", peer)
    finally:
        try:
            conn.close()
        except Exception:
            pass
        logging.info("Client disconnected: %s", peer)

def serve(host: str, port: int):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        s.listen(BACKLOG)
        logging.info("Listening on %s:%d", host, port)
        threads = []
        try:
            while True:
                conn, addr = s.accept()
                t = threading.Thread(target=client_thread, args=(conn, addr), daemon=True)
                t.start()
                threads.append(t)
        except KeyboardInterrupt:
            logging.info("Shutting down server")
        finally:
            for t in threads:
                t.join(timeout=0.1)

def main():
    parser = argparse.ArgumentParser(description="AUBus JSON-L server (no tokens)")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=6000)
    parser.add_argument("--log", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log.upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(message)s")

    serve(args.host, args.port)

if __name__ == "__main__":
    main()
