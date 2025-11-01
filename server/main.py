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

# ---------------------------
# Constants and configuration
# ---------------------------

ENCODING = "utf-8"           # Encoding for text over sockets
BACKLOG = 10                 # Max queued connections in listen()
RECV_BUFSIZE = 4096          # How much to read from socket each recv()


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
