#!/usr/bin/env python3
import json, socket, uuid, argparse, sys, time

ENCODING = "utf-8"
RECV_BUFSIZE = 4096

def send_json(sock, obj):
    data = (json.dumps(obj, separators=(",", ":")) + "\n").encode(ENCODING)
    sock.sendall(data)

def recv_json(sock):
    buf = b""
    while True:
        chunk = sock.recv(RECV_BUFSIZE)
        if not chunk:
            raise ConnectionResetError("server closed connection")
        buf += chunk
        if b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            return json.loads(line.decode(ENCODING).strip())

def make_req(msg_type, payload):
    return {"type": msg_type, "id": str(uuid.uuid4()), "payload": payload}

def do_case(sock, title, msg_type, payload):
    req = make_req(msg_type, payload)
    print(f"\n=== {title} ===")
    print("→", json.dumps(req, indent=2))
    send_json(sock, req)
    resp = recv_json(sock)
    print("←", json.dumps(resp, indent=2))
    return resp

def with_socket(host, port, fn):
    s = socket.create_connection((host, port))
    try:
        return fn(s)
    finally:
        s.close()
        time.sleep(0.05)  # small pause so server logs are tidy

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=6000)
    ap.add_argument("--area", default="Hamra")
    args = ap.parse_args()

    # Unique user so the script is re-runnable
    suf = uuid.uuid4().hex[:6]
    username_ok = f"hayam_login_{suf}"
    email_ok = f"hayam.login+{suf}@example.com"
    password_ok = "password123"

    # 0) Prepare: register a valid user we can log into
    def register_once(sock):
        payload = {
            "name": "Hayam",
            "email": email_ok,
            "username": username_ok,
            "password": password_ok,
            "area": args.area
        }
        return do_case(sock, "PREP: register user for login tests",
                       "AUTH.REGISTER_REQ", payload)

    with_socket(args.host, args.port, register_once)

    # 1) LOGIN OK
    def login_ok(sock):
        payload = {"username": username_ok, "password": password_ok}
        do_case(sock, "LOGIN OK: correct username/password",
                "AUTH.LOGIN_REQ", payload)

    with_socket(args.host, args.port, login_ok)

    # 2) LOGIN FAIL: wrong password
    def login_wrong_pass(sock):
        payload = {"username": username_ok, "password": "wrongpass"}
        do_case(sock, "LOGIN ERR: wrong password",
                "AUTH.LOGIN_REQ", payload)

    with_socket(args.host, args.port, login_wrong_pass)

    # 3) LOGIN FAIL: unknown user
    def login_unknown_user(sock):
        payload = {"username": f"no_such_{suf}", "password": password_ok}
        do_case(sock, "LOGIN ERR: unknown username",
                "AUTH.LOGIN_REQ", payload)

    with_socket(args.host, args.port, login_unknown_user)

    # 4) LOGIN FAIL: missing fields
    def login_missing_fields(sock):
        payloads = [
            {"password": password_ok},             # missing username
            {"username": username_ok},             # missing password
            {"username": "", "password": password_ok},  # empty username
            {"username": username_ok, "password": ""},  # empty password
        ]
        for i, p in enumerate(payloads, 1):
            do_case(sock, f"LOGIN ERR: missing/empty field case {i}",
                    "AUTH.LOGIN_REQ", p)

    with_socket(args.host, args.port, login_missing_fields)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
