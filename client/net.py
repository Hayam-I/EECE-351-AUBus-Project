#!/usr/bin/env python3
"""
AUBus – Minimal client scaffold (Phase 0)
-----------------------------------------
Connects to the JSON Lines TCP server, sends/receives JSON messages,
and handles simple backoff retry on connection loss.

This version performs a self-test:
  → connects to localhost:6000
  → sends {"type":"PING"} with a UUID
  → prints the server's response
"""

import json
import logging
import socket
import time
import uuid

# -------------------------
# Constants and parameters
# -------------------------
ENCODING = "utf-8"
RECV_BUFSIZE = 4096
BACKOFFS = [0.2, 0.5, 1.0]  # seconds

# -------------------------
# Helper functions
# -------------------------
def send_json(sock: socket.socket, obj: dict):
    """
    Serialize and send one JSON object (newline-terminated).
    """
    data = (json.dumps(obj, separators=(",", ":")) + "\n").encode(ENCODING)
    sock.sendall(data)
    logging.debug("→ %s", obj.get("type"))


def recv_json(sock: socket.socket):
    """
    Receive one line-delimited JSON object from the socket.
    """
    buf = b""
    while True:
        chunk = sock.recv(RECV_BUFSIZE)
        if not chunk:
            raise ConnectionResetError("Server closed connection")
        buf += chunk
        if b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            msg = json.loads(line.decode(ENCODING, errors="replace").strip())
            logging.debug("← %s", msg.get("type"))
            return msg


def connect_with_backoff(host: str, port: int):
    """
    Try connecting to the server with backoff intervals.
    Returns a connected socket or raises after last attempt.
    """
    for delay in BACKOFFS:
        try:
            sock = socket.create_connection((host, port))
            logging.info("Connected to %s:%d", host, port)
            return sock
        except ConnectionRefusedError:
            logging.warning("Connection refused, retrying in %.1fs...", delay)
            time.sleep(delay)
    raise ConnectionRefusedError(f"Failed to connect to {host}:{port} after retries")


# -------------------------
# Main client routine
# -------------------------
def main():
    host = "127.0.0.1"
    port = 6000

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s"
    )

    try:
        sock = connect_with_backoff(host, port)

        # Build a PING message with UUID
        msg = {
            "type": "PING",
            "id": str(uuid.uuid4()),
            "payload": {}
        }
        send_json(sock, msg)

        # Wait for response
        resp = recv_json(sock)
        print("Server replied:", json.dumps(resp, indent=2))

    except Exception as e:
        logging.error("Client error: %s", e)
    finally:
        try:
            sock.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
