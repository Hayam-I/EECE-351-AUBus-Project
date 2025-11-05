#!/usr/bin/env python3
"""
AUBus – Server (Phase 0 + P1-05)
--------------------------------
Multi-threaded TCP server using JSON Lines.
Supports:
  • PING
  • AUTH.REGISTER_REQ / AUTH.LOGIN_REQ
  • PROFILE.SET_REQ (auth required)
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
from threading import Lock

# ---------------- Configuration ----------------
ENCODING = "utf-8"
BACKLOG = 10
RECV_BUFSIZE = 4096
DB_PATH = "database.db"

# Simple in-memory token map (for now)
SESSION_TOKENS = {"dev_token_123": 1}  # user_id 1 must exist in users

# --------------- UUID validator ----------------
def is_valid_uuid4(value: str) -> bool:
    if not isinstance(value, str):
        return False
    try:
        u = uuid.UUID(value, version=4)
    except (ValueError, TypeError):
        return False
    return str(u) in (value, value.lower(), value.upper())

# --------------- Socket helpers ----------------
def recv_lines(sock: socket.socket):
    buf = b""
    while True:
        chunk = sock.recv(RECV_BUFSIZE)
        if not chunk:
            return
        logging.debug("recv_lines: got %d bytes", len(chunk))
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            yield line.decode(ENCODING, errors="replace").rstrip("\r").strip()

def send_json(sock: socket.socket, obj: dict):
    data = (json.dumps(obj, separators=(",", ":")) + "\n").encode(ENCODING)
    sock.sendall(data)

# --------------- Validation helpers (register) ---------------
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,20}$")
PASSWORD_RE = re.compile(r"^.{6,20}$")
EMAIL_RE    = re.compile(r"^[^@]+@[^@]+\.[^@]+$")

def validate_register_payload(p):
    missing = [k for k in ("name","email","username","password","area") if k not in p]
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

# --------------- DB operations -----------------
def register_user(p):
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
        return True, {"user_id": f"user_{cur.lastrowid}"}
    finally:
        conn.close()

def _user_preview_from_row(row):
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

def login_user(p):
    for k in ("username","password"):
        if k not in p or not isinstance(p[k], str) or not p[k]:
            return False, {"code": "BAD_REQUEST","message":f"Missing/invalid field: {k}"}
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
            return False, {"code": "AUTH_INVALID_CREDENTIALS","message":"Invalid username or password"}
        return True, {"user": _user_preview_from_row(row)}
    finally:
        conn.close()

# --------------- PROFILE.SET_REQ handler -----------------
def handle_profile_set(msg: dict) -> dict:
    mid = msg.get("id")
    auth = msg.get("auth") or {}
    token = auth.get("token")

    if not token or token not in SESSION_TOKENS:
        return {
            "type": "ERROR",
            "id": mid,
            "payload": {"code": "AUTH_REQUIRED", "message": "Missing or invalid token"},
        }

    user_id = SESSION_TOKENS[token]
    p = msg.get("payload") or {}
    name = p.get("name")
    email = p.get("email")
    area = p.get("area")
    is_driver = 1 if p.get("is_driver") else 0

    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET name=?, email=?, area=?, is_driver=? WHERE user_id=?",
            (name, email, area, is_driver, user_id),
        )
        conn.commit()
        cur.execute("SELECT name,email,area,is_driver FROM users WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return {"type":"ERROR","id":mid,
                    "payload":{"code":"NOT_FOUND","message":"User not found"}}
        stored = {"name":row[0],"email":row[1],"area":row[2],"is_driver":row[3]}
        return {"type":"PROFILE_OK","id":mid,"payload":stored}
    except Exception as e:
        logging.error("DB error in PROFILE.SET_REQ: %s", e, exc_info=True)
        return {"type":"ERROR","id":mid,
                "payload":{"code":"DB_ERROR","message":"Failed to update profile"}}

# --------------- Message dispatcher -----------------
def handle_message(msg: dict):
    required = ("type","id")
    missing = [k for k in required if k not in msg]
    if missing:
        return {"type":"ERROR","id":msg.get("id"),
                "payload":{"code":"BAD_REQUEST","message":f"Missing: {', '.join(missing)}"}}
    if not is_valid_uuid4(msg["id"]):
        return {"type":"ERROR","id":msg["id"],
                "payload":{"code":"BAD_REQUEST","message":"Invalid UUIDv4"}}

    mtype = msg["type"]
    mid = msg["id"]

    if mtype == "PING":
        return {"type":"PONG","id":mid,"payload":{}}
    elif mtype == "AUTH.REGISTER_REQ":
        ok,res = register_user(msg.get("payload",{}))
        return {"type":"AUTH.REGISTER_RES" if ok else "ERROR","id":mid,"payload":res}
    elif mtype == "AUTH.LOGIN_REQ":
        ok,res = login_user(msg.get("payload",{}))
        return {"type":"AUTH.LOGIN_RES" if ok else "ERROR","id":mid,"payload":res}
    elif mtype == "PROFILE.SET_REQ":
        return handle_profile_set(msg)

    return {"type":"ERROR","id":mid,
            "payload":{"code":"UNKNOWN_TYPE","message":f"Unsupported type: {mtype}"}}

# --------------- Thread per client -----------------
def client_thread(conn: socket.socket, addr):
    peer = f"{addr[0]}:{addr[1]}"
    logging.info("Client connected: %s", peer)
    try:
        for line in recv_lines(conn):
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                send_json(conn, {"type":"ERROR","id":None,
                                 "payload":{"code":"BAD_JSON","message":"Invalid JSON line"}})
                continue
            try:
                resp = handle_message(msg)
            except Exception:
                logging.error("Handler error:\n%s", traceback.format_exc())
                resp = {"type":"ERROR","id":msg.get("id"),
                        "payload":{"code":"SERVER_ERROR","message":"Internal error"}}
            send_json(conn, resp)
    except (ConnectionResetError,BrokenPipeError):
        pass
    finally:
        conn.close()
        logging.info("Client disconnected: %s", peer)

# --------------- Server loop -----------------
def serve(host: str, port: int):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        s.listen(BACKLOG)
        logging.info("Listening on %s:%d", host, port)
        threads=[]
        try:
            while True:
                conn, addr = s.accept()
                t = threading.Thread(target=client_thread,args=(conn,addr),daemon=True)
                t.start()
                threads.append(t)
        except KeyboardInterrupt:
            logging.info("Shutting down server")
        finally:
            for t in threads:
                t.join(timeout=0.1)

# --------------- Entry point -----------------
def main():
    parser = argparse.ArgumentParser(description="AUBus server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=6000)
    parser.add_argument("--log", default="INFO")
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log.upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(message)s")
    serve(args.host, args.port)

if __name__ == "__main__":
    main()
