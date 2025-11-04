#!/usr/bin/env python3
"""
AUBus – Server scaffold (P0-03 + P1-05)
---------------------------------------
- JSON Lines over TCP, multi-threaded
- PING -> PONG
- PROFILE.SET_REQ (auth required) -> PROFILE_OK
  payload fields: name, email, area, is_driver(bool)
"""

import argparse
import json
import logging
import socket
import threading
import traceback
import os

# Try to use project DB helpers if available; otherwise fall back to in-memory.
USE_DB = True
try:
    import db.db as db  # expects execute(), query_one()
except Exception:
    USE_DB = False

ENCODING = "utf-8"
BACKLOG = 10
RECV_BUFSIZE = 4096

# --------------------------------------------------------------------
# Minimal auth/session store (replace with your LOGIN_REQ logic later)
# --------------------------------------------------------------------
# For testing P1-05 quickly, we expose a default token → user_id mapping.
# If you already have LOGIN producing tokens, populate SESSION_TOKENS there.
SESSION_TOKENS = {
    # dev token used by your test script
    "dev_token_123": 1,
}

# In-memory fallback user store only used when DB module isn't available.
INMEM_USERS = {
    1: {"name": "Test User", "email": "test@example.com", "area": "Beirut", "is_driver": 0}
}

# ---------------- JSON-L helpers ----------------
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
            logging.debug("recv_lines: emitting line: %r", line)
            yield line.decode(ENCODING, errors="replace").rstrip("\r").strip()

def send_json(sock: socket.socket, obj: dict):
    data = (json.dumps(obj, separators=(",", ":")) + "\n").encode(ENCODING)
    sock.sendall(data)

# ---------------- Message handlers ----------------
def handle_profile_set(msg: dict) -> dict:
    """
    PROFILE.SET_REQ:
      - auth.token required -> resolves to user_id
      - update name, email, area, is_driver
      - return PROFILE_OK with stored values
    """
    mid = msg.get("id")
    auth = (msg.get("auth") or {})
    token = auth.get("token")
    if not token or token not in SESSION_TOKENS:
        return {
            "type": "ERROR",
            "id": mid,
            "payload": {"code": "AUTH_REQUIRED", "message": "Missing or invalid token"},
        }

    user_id = SESSION_TOKENS[token]
    payload = msg.get("payload") or {}
    name = payload.get("name")
    email = payload.get("email")
    area = payload.get("area")
    is_driver = 1 if payload.get("is_driver") else 0

    if USE_DB:
        try:
            # Update users row
            db.execute(
                "UPDATE users SET name=?, email=?, area=?, is_driver=? WHERE id=?",
                (name, email, area, is_driver, user_id),
            )
            row = db.query_one(
                "SELECT name, email, area, is_driver FROM users WHERE id=?",
                (user_id,),
            )
            stored = dict(row) if row else {
                "name": name, "email": email, "area": area, "is_driver": is_driver
            }
        except Exception as e:
            logging.error("DB error in PROFILE.SET_REQ: %s", e, exc_info=True)
            return {
                "type": "ERROR",
                "id": mid,
                "payload": {"code": "DB_ERROR", "message": "Failed to persist profile"},
            }
    else:
        # In-memory fallback so you can test P1-05 immediately
        u = INMEM_USERS.setdefault(user_id, {"name": None, "email": None, "area": None, "is_driver": 0})
        if name is not None: u["name"] = name
        if email is not None: u["email"] = email
        if area is not None: u["area"] = area
        u["is_driver"] = is_driver
        stored = dict(u)

    return {"type": "PROFILE_OK", "id": mid, "payload": stored}

def handle_message(msg: dict) -> dict:
    mtype = msg.get("type")
    mid = msg.get("id")

    if mtype == "PING":
        return {"type": "PONG", "id": mid, "payload": {}}
    elif mtype == "PROFILE.SET_REQ":
        return handle_profile_set(msg)

    return {
        "type": "ERROR",
        "id": mid,
        "payload": {"code": "UNKNOWN_TYPE", "message": f"Unsupported type: {mtype}"},
    }

# --------------- Client thread & server loop ---------------
def client_thread(conn: socket.socket, addr):
    peer = f"{addr[0]}:{addr[1]}"
    logging.info("Client connected: %s", peer)
    try:
        for line in recv_lines(conn):
            if not line:
                logging.debug("Blank line from %s; ignoring", peer)
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                logging.warning("Bad JSON from %s: %r", peer, line)
                send_json(conn, {
                    "type": "ERROR",
                    "id": None,
                    "payload": {"code": "BAD_JSON", "message": "Invalid JSON line"},
                })
                continue
            logging.debug("← %s %s", peer, msg.get("type"))
            try:
                resp = handle_message(msg)
            except Exception:
                logging.error("Handler error:\n%s", traceback.format_exc())
                resp = {
                    "type": "ERROR",
                    "id": msg.get("id"),
                    "payload": {"code": "SERVER_ERROR", "message": "Internal error"},
                }
            send_json(conn, resp)
            logging.debug("→ %s %s", peer, resp.get("type"))
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
            logging.info("Shutting down server (KeyboardInterrupt)")
        finally:
            for t in threads:
                t.join(timeout=0.1)

def main():
    parser = argparse.ArgumentParser(description="AUBus JSON-L server")
    parser.add_argument("--host", default="0.0.0.0", help="Host/IP to bind")
    parser.add_argument("--port", type=int, default=6000, help="Port to listen on")
    parser.add_argument("--log", default="INFO", help="Logging level (DEBUG, INFO, WARNING, ERROR)")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.info("Running file: %s", os.path.abspath(__file__))
    logging.info("Parsed args → host=%s port=%s log=%s", args.host, args.port, args.log)

    serve(args.host, args.port)

if __name__ == "__main__":
    main()
