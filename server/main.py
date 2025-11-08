#!/usr/bin/env python3
"""
AUBus – Server (Phase 0 + P1-05, NO TOKENS)
-------------------------------------------
Transport: TCP + JSON Lines (one connection per client)

Envelope (all messages):
  { "type": "<MessageType>", "id": "<UUIDv4>", "payload": {...}? }

Auth model (per-connection):
  • After AUTH.LOGIN_RES, we bind THIS TCP connection to that user_id.
  • PROFILE.SET/GET require the connection to be logged in (unless GET specifies a user_id and we allow public lookups — here we keep it "login required" by default).

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

# ---------------------------
# Constants and configuration
# ---------------------------
ENCODING = "utf-8"
BACKLOG = 10
RECV_BUFSIZE = 4096
DB_PATH = "database.db"

# ---------------------------
# UUIDv4 validation
# ---------------------------
def is_valid_uuid4(value: str) -> bool:
    if not isinstance(value, str):
        return False
    try:
        u = uuid.UUID(value, version=4)
    except (ValueError, TypeError):
        return False
    return str(u) in (value, value.lower(), value.upper())

# ---------------------------------------------------------
# JSON-L helpers
# ---------------------------------------------------------
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

# ---------------------------------------------------------
# Validation helpers (registration/login)
# ---------------------------------------------------------
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,20}$")
PASSWORD_RE = re.compile(r"^.{6,20}$")
EMAIL_RE    = re.compile(r"^[^@]+@[^@]+\.[^@]+$")

def validate_register_payload(p: dict):
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

# ---------------------------------------------------------
# DB utilities
# ---------------------------------------------------------
def register_user(p: dict):
    ok, msg = validate_register_payload(p)
    if not ok:
        return False, {"code": "BAD_REQUEST", "message": msg}
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO users (name, username, password, email, is_driver, area) "
                "VALUES (?, ?, ?, ?, 0, ?)",
                (p["name"], p["username"], p["password"], p["email"], p["area"]),
            )
            conn.commit()
        except sqlite3.IntegrityError as e:
            err = str(e).lower()
            if "username" in err:
                return False, {"code": "AUTH_USERNAME_TAKEN", "message": "Username already exists"}
            if "email" in err:
                return False, {"code": "AUTH_EMAIL_TAKEN", "message": "Email already exists"}
            return False, {"code": "SERVER_ERROR", "message": "Database error"}
        new_user_id = cur.lastrowid
        return True, {"user_id": f"user_{new_user_id}"}
    finally:
        conn.close()

def _user_preview_from_row(row):
    # row = (user_id, name, username, password, email, is_driver, area, rating_sum, rating_avg, rating_count)
    return {
        "user_id": f"user_{row[0]}",
        "name": row[1],
        "username": row[2],
        "email": row[4],
        "is_driver": bool(row[5]),
        "area": row[6],
        "rating_sum": row[7],
        "rating_avg": float(row[8]) if row[8] is not None else 0.0,
        "rating_count": row[9],
    }

def login_user(p: dict):
    for k in ("username", "password"):
        if k not in p or not isinstance(p[k], str) or not p[k]:
            return False, {"code": "BAD_REQUEST", "message": f"Missing/invalid field: {k}"}
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT user_id,name,username,password,email,is_driver,area,rating_sum,rating_avg,rating_count "
            "FROM users WHERE username=?",
            (p["username"],),
        )
        row = cur.fetchone()
        if not row or row[3] != p["password"]:
            return False, {"code": "AUTH_INVALID_CREDENTIALS", "message": "Invalid username or password"}
        return True, {"user": _user_preview_from_row(row), "user_id_int": int(row[0])}
    finally:
        conn.close()

# ---------------------------------------------------------
# PROFILE handlers (connection must be logged in)
# ---------------------------------------------------------
def profile_set(user_id: int, payload: dict, mid):
    if not user_id:
        return {"type": "ERROR", "id": mid, "payload": {"code": "FORBIDDEN", "message": "Login required"}}

    p = payload or {}
    # Allowed top-level fields (all optional except area here)
    name      = p.get("name")
    email     = p.get("email")
    area      = p.get("area")
    is_driver = 1 if p.get("is_driver") else 0
    vehicle   = p.get("vehicle") or {}

    v_make  = vehicle.get("make")
    v_model = vehicle.get("model")
    v_color = vehicle.get("color")
    v_plate = vehicle.get("plate")

    if not isinstance(area, str) or not area:
        return {"type": "ERROR", "id": mid, "payload": {"code": "PROFILE_AREA_REQUIRED", "message": "area is required"}}

    try:
        conn = sqlite3.connect(DB_PATH)
        cur  = conn.cursor()

        # Update main user record (COALESCE preserves existing when None)
        cur.execute(
            "UPDATE users SET name=COALESCE(?,name), email=COALESCE(?,email), area=?, is_driver=? WHERE user_id=?",
            (name, email, area, is_driver, user_id),
        )

        # Upsert into profiles table
        cur.execute("SELECT 1 FROM profiles WHERE user_id=?", (user_id,))
        if cur.fetchone():
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

        conn.commit()
        conn.close()
        return {"type": "PROFILE.SET_RES", "id": mid, "payload": {}}
    except Exception as e:
        logging.exception("profile_set failed")
        return {"type": "ERROR", "id": mid, "payload": {"code": "SERVER_ERROR", "message": "Failed to update profile"}}

def profile_get(current_user_id: int, payload: dict, mid):
    # If payload contains user_id like "user_7" we'll read that; otherwise default to current connection user.
    p = payload or {}
    target_uid = None
    if isinstance(p.get("user_id"), str) and p["user_id"].startswith("user_"):
        try:
            target_uid = int(p["user_id"].split("_", 1)[1])
        except ValueError:
            return {"type": "ERROR", "id": mid, "payload": {"code": "BAD_REQUEST", "message": "Invalid user_id format"}}
    else:
        target_uid = current_user_id

    if not target_uid:
        return {"type": "ERROR", "id": mid, "payload": {"code": "FORBIDDEN", "message": "Login required or provide user_id"}}

    try:
        conn = sqlite3.connect(DB_PATH)
        cur  = conn.cursor()
        cur.execute(
            "SELECT user_id,name,username,password,email,is_driver,area,rating_sum,rating_avg,rating_count "
            "FROM users WHERE user_id=?",
            (target_uid,),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return {"type": "ERROR", "id": mid, "payload": {"code": "NOT_FOUND", "message": "User not found"}}
        user = {
            "user_id": f"user_{row[0]}",
            "name": row[1],
            "area": row[6],
            "is_driver": bool(row[5]),
            "rating": float(row[8]) if row[8] is not None else 0.0,
        }
        return {"type": "PROFILE.GET_RES", "id": mid, "payload": {"user": user}}
    except Exception:
        logging.exception("profile_get failed")
        return {"type": "ERROR", "id": mid, "payload": {"code": "SERVER_ERROR", "message": "Internal error"}}

# ---------------------------------------------------------
# Dispatcher (takes per-connection state)
# ---------------------------------------------------------
def handle_message(msg: dict, conn_state: dict):
    if "type" not in msg or "id" not in msg:
        return {"type": "ERROR", "id": msg.get("id"),
                "payload": {"code": "BAD_REQUEST", "message": "Missing required field(s): type, id"}}
    if not is_valid_uuid4(msg["id"]):
        return {"type": "ERROR", "id": msg.get("id"),
                "payload": {"code": "BAD_REQUEST", "message": "Field 'id' must be a valid UUIDv4 string"}}

    mtype   = msg["type"]
    mid     = msg["id"]
    payload = msg.get("payload") or {}

    # CONTROL
    if mtype == "PING":
        return {"type": "PONG", "id": mid, "payload": {}}

    # AUTH
    if mtype == "AUTH.REGISTER_REQ":
        ok, res = register_user(payload)
        return {"type": "AUTH.REGISTER_RES" if ok else "ERROR", "id": mid, "payload": res}

    if mtype == "AUTH.LOGIN_REQ":
        ok, res = login_user(payload)
        if ok:
            conn_state["user_id"] = res["user_id_int"]  # bind this socket to the user
            # Don't leak the internal int in payload; return only user preview
            return {"type": "AUTH.LOGIN_RES", "id": mid, "payload": {"user": res["user"]}}
        else:
            return {"type": "ERROR", "id": mid, "payload": res}

    if mtype == "AUTH.LOGOUT_REQ":
        conn_state["user_id"] = None
        return {"type": "AUTH.LOGOUT_RES", "id": mid, "payload": {"message": "Logout Successful"}}

    # PROFILE (require connection-bound login)
    if mtype == "PROFILE.SET_REQ":
        return profile_set(conn_state.get("user_id"), payload, mid)

    if mtype == "PROFILE.GET_REQ":
        return profile_get(conn_state.get("user_id"), payload, mid)

    # Unknown
    return {"type": "ERROR", "id": mid, "payload": {"code": "UNKNOWN_TYPE", "message": f"Unsupported type: {mtype}"}}

# ---------------------------------------------------------
# Per-client thread & server
# ---------------------------------------------------------
def client_thread(conn: socket.socket, addr):
    peer = f"{addr[0]}:{addr[1]}"
    logging.info("Client connected: %s", peer)

    # Per-connection state (no tokens; socket-bound)
    conn_state = {"user_id": None}

    try:
        for line in recv_lines(conn):
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                send_json(conn, {"type": "ERROR", "id": None, "payload": {"code": "BAD_JSON", "message": "Invalid JSON line"}})
                continue
            try:
                resp = handle_message(msg, conn_state)
            except Exception:
                logging.error("Handler error:\n%s", traceback.format_exc())
                resp = {"type": "ERROR", "id": msg.get("id"), "payload": {"code": "SERVER_ERROR", "message": "Internal error"}}
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
    parser = argparse.ArgumentParser(description="AUBus JSON-L server (no tokens; connection-bound auth)")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=6000)
    parser.add_argument("--log", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log.upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(message)s")

    serve(args.host, args.port)

if __name__ == "__main__":
    main()
