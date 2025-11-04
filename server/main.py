#!/usr/bin/env python3
"""
AUBus – Minimal server scaffold (Phase 0)
----------------------------------------
Implements a multi-threaded TCP server using JSON Lines protocol.
Handles only 'PING' requests at this stage, replies with 'PONG'.

Each message:
  { "type": <str>, "id": <uuid>, "payload": {...} }

Future phases will add REGISTER, LOGIN, RIDE_REQUEST, etc.
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

# ---------------------------
# Constants and configuration
# ---------------------------

ENCODING = "utf-8"           # Encoding for text over sockets
BACKLOG = 10                 # Max queued connections in listen()
RECV_BUFSIZE = 4096          # How much to read from socket each recv()

DB_PATH =  "database.db" # Path to SQLite database file



import db.database as db  # adjust import path if needed

# Example in-memory token store (created earlier in login handler)
SESSION_TOKENS = {}  # token:str -> user_id:int

def handle_profile_set(msg: dict):
    """
    Handles PROFILE.SET_REQ: updates user profile fields and returns PROFILE_OK
    """
    mid = msg.get("id")
    auth = msg.get("auth") or {}
    token = auth.get("token")

    # --- auth check ---
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
    is_driver = bool(payload.get("is_driver", False))

    # --- update database ---
    sql = """
        UPDATE users
        SET name=?, email=?, area=?, is_driver=?
        WHERE id=?
    """
    db.execute(sql, (name, email, area, int(is_driver), user_id))

    # --- read back stored values for confirmation ---
    row = db.query_one("SELECT name, email, area, is_driver FROM users WHERE id=?", (user_id,))

    return {"type": "PROFILE_OK", "id": mid, "payload": dict(row)}





#adding section for uuid validation
def is_valid_uuid4(value: str) -> bool:
    """
    Returns True if `value` is a canonical UUIDv4 string (lower/upper case accepted).
    Accepts only a 36-character hex format with hyphens (the usual str(UUID) form).
    """
    if not isinstance(value, str):
        return False
    try:
        u = uuid.UUID(value, version=4)
    except (ValueError, TypeError):
        return False
    # Ensure the textual form matches exactly (normalizes case)
    return str(u) == value.lower() or str(u) == value.upper() or str(u) == value
#end of added section

# ---------------------------------------------------------
# Utility generator to read newline-delimited JSON messages
# ---------------------------------------------------------
def recv_lines(sock: socket.socket):
    """
    Continuously receive data from a socket and yield each line as soon as a newline ('\\n')
    is encountered. This allows us to send multiple JSON messages without closing the socket.
    """
    buf = b""
    while True:
        # Read raw bytes from socket
        chunk = sock.recv(RECV_BUFSIZE)
        if not chunk:
            return  # client closed connection

        logging.debug("recv_lines: got %d bytes", len(chunk))
        buf += chunk

        # Split buffer by newline, keep remainder
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            logging.debug("recv_lines: emitting line: %r", line)

            # Decode to str and yield for processing
            yield line.decode(ENCODING, errors="replace").rstrip("\r").strip()


# ----------------------------------------------------------
# Utility to send a JSON object as one line (JSON Lines style)
# ----------------------------------------------------------
def send_json(sock: socket.socket, obj: dict):
    """
    Serialize `obj` to compact JSON, append newline, and send over socket.
    """
    data = (json.dumps(obj, separators=(",", ":")) + "\n").encode(ENCODING)
    sock.sendall(data)


# ------------------------------------------------------
# Main message handler (extend later with real commands)
# ------------------------------------------------------

#validating registration of new users
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,20}$") #the username can contain letters, numbers, and underscores, and must be between 5 and 20 characters long
PASSWORD_RE = re.compile(r"^.{6,20}$") #the password must be between 6 and 50 characters long
EMAIL_RE = re.compile(r"^[^@]+@[^@]+\.[^@]+$") #email must be string@string.string 
def validate_register_payload(p):
    missing = [k for k in ("name", "email", "username", "password", "area") if k not in p]
    if missing:
        return False, f"Missing fields: {', '.join(missing)}"
    if not USERNAME_RE.match(p["username"]):
        return False, "Invalid username (5-20 letters/digists/underscores)"
    if not PASSWORD_RE.match(p["password"]):
        return False, "Invalid password (6-20 characters)"
    if not EMAIL_RE.match(p["email"]):
        return False, "Invalid email format"
    if not isinstance(p["area"], str) or not p["area"]:
        return False, "Area must be a non-empty string"
    return True, ""

#adding a user into db, making sure username and email and password are valid and username/email are unique 
def register_user(p):
    ok, msg = validate_register_payload(p)
    if not ok:
        return False, {"code": "BAD_REQUEST", "message": msg}
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO users (username, password, email, is_driver, area) VALUES (?, ?, ?, 0, ?)""", #other not null fileds will be 0 by default (for ratings)
                (p["username"], p["password"], p["email"], p["area"])
            )
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

def handle_message(msg: dict):
    """
    Inspect message type and build an appropriate response.
    For now supports only:
      PING → PONG
      anything else → ERROR
    """
    #adding this section to check for required fields: type and id, payload is optional for some messages so we cant enforce it.
    required_fields = ("type", "id")
    missing = [key for key in required_fields if key not in msg]

    if missing:
        return {
            "type": "ERROR",
            "id": msg.get("id"),  # may be None if missing
            "payload": {
                "code": "BAD_REQUEST",
                "message": f"Missing required field(s): {', '.join(missing)}"
            }
        }
    if not is_valid_uuid4(msg["id"]):
        return {
            "type": "ERROR",
            "id": msg.get("id"),
            "payload": {
                "code": "BAD_REQUEST",
                "message": "Field 'id' must be a valid UUIDv4 string"
            }
        }
        #end of added section

    
    mtype = msg.get("type")
    mid = msg.get("id")

    if mtype == "PING":
        # Standard healthy reply
        return {"type": "PONG", "id": mid, "payload": {}}
    elif mtype == "PROFILE.SET_REQ":
        return handle_profile_set(msg)
    
    #adding user into db upon registration request, defining the response message
    if mtype == "AUTH.REGISTER_REQ":
        p = msg.get("payload", {})
        ok, result = register_user(p)
        if ok:
            return {"type": "AUTH.REGISTER_RES", "id": mid, "payload": result}
        else:
            return {"type": "ERROR", "id": mid, "payload": result}


    # Unknown message type – return a structured error
    return {
        "type": "ERROR",
        "id": mid,
        "payload": {"code": "UNKNOWN_TYPE", "message": f"Unsupported type: {mtype}"},  
    }




# ------------------------------------------
# Thread target: handles one connected client
# ------------------------------------------
def client_thread(conn: socket.socket, addr):
    """
    Each client runs in its own thread.
    Reads JSON messages line-by-line and replies immediately.
    """
    peer = f"{addr[0]}:{addr[1]}"
    logging.info("Client connected: %s", peer)

    try:
        # Loop over messages coming from this client
        for line in recv_lines(conn):
            # Ignore blank lines instead of breaking
            if not line:
                logging.debug("Blank line from %s; ignoring", peer)
                continue

            try:
                # Parse the received JSON line
                msg = json.loads(line)
            except json.JSONDecodeError:
                # If it's invalid JSON, return an ERROR response
                logging.warning("Bad JSON from %s: %r", peer, line)
                send_json(conn, {
                    "type": "ERROR",
                    "id": None,
                    "payload": {"code": "BAD_JSON", "message": "Invalid JSON line"},
                })
                continue

            mtype = msg.get("type")
            logging.debug("← %s %s", peer, mtype)

            try:
                # Delegate message handling to handle_message()
                resp = handle_message(msg)
            except Exception:
                # Defensive: catch unexpected exceptions to avoid crashing thread
                logging.error("Handler error:\n%s", traceback.format_exc())
                resp = {
                    "type": "ERROR",
                    "id": msg.get("id"),
                    "payload": {"code": "SERVER_ERROR", "message": "Internal error"},
                }

            # Send the response back to the same client
            send_json(conn, resp)
            logging.debug("→ %s %s", peer, resp.get("type"))

    except (ConnectionResetError, BrokenPipeError):
        # Client disconnected abruptly
        logging.info("Client reset: %s", peer)

    finally:
        # Always close socket at the end
        try:
            conn.close()
        except Exception:
            pass
        logging.info("Client disconnected: %s", peer)


# ------------------------------------------
# Main accept loop – listens for new clients
# ------------------------------------------
def serve(host: str, port: int):
    """
    Open a TCP listener, accept new clients, and spawn a thread for each one.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        # Allow immediate restart of the server after crash/restart
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        s.listen(BACKLOG)
        logging.info("Listening on %s:%d", host, port)

        threads = []
        try:
            # Infinite accept loop
            while True:
                conn, addr = s.accept()
                # Launch new daemon thread for each connected client
                t = threading.Thread(target=client_thread, args=(conn, addr), daemon=True)
                t.start()
                threads.append(t)
        except KeyboardInterrupt:
            logging.info("Shutting down server (KeyboardInterrupt)")
        finally:
            # Wait briefly for threads to exit (they're daemon so process exits anyway)
            for t in threads:
                t.join(timeout=0.1)


def query_one(sql, params=()):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(sql, params)
    row = cur.fetchone()
    conn.commit()
    return row


# ------------------------------
# Command-line entry point
# ------------------------------
def main():
    parser = argparse.ArgumentParser(description="AUBus minimal JSON-L server")
    parser.add_argument("--host", default="0.0.0.0", help="Host/IP to bind")
    parser.add_argument("--port", type=int, default= 6000, help="Port to listen on")
    parser.add_argument("--log", default="INFO", help="Logging level (DEBUG, INFO, WARNING, ERROR)")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    serve(args.host, args.port)


if __name__ == "__main__":
    main()
