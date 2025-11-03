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

def do_case(sock, title, payload):
    req = make_req("AUTH.REGISTER_REQ", payload)
    print(f"\n=== {title} ===")
    print("→", json.dumps(req, indent=2))
    send_json(sock, req)
    resp = recv_json(sock)
    print("←", json.dumps(resp, indent=2))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=6000)
    ap.add_argument("--area", default="Hamra")
    args = ap.parse_args()

    # New socket per case to mimic normal client sessions
    def with_socket(fn):
        s = socket.create_connection((args.host, args.port))
        try:
            fn(s)
        finally:
            s.close()
            time.sleep(0.05)  # tiny pause so server logs look clean

    # Unique suffix so you can rerun script repeatedly without collisions
    suf = uuid.uuid4().hex[:6]
    base_user = f"hayam_{suf}"
    base_mail = f"hayam+{suf}@example.com"

    # 1) Base case: path (should succeed)
    with_socket(lambda s: do_case(
        s, "OK: fresh username+email",
        {"name":"Hayam","email":base_mail,"username":base_user,"password":"password123","area":args.area}
    ))

    # 2) Duplicate username (should error AUTH_USERNAME_TAKEN)
    with_socket(lambda s: do_case(
        s, "ERROR: duplicate username",
        {"name":"Other","email":f"other+{suf}@example.com","username":base_user,"password":"password123","area":args.area}
    ))

    # 3) Duplicate email (should error AUTH_EMAIL_TAKEN)
    with_socket(lambda s: do_case(
        s, "ERROR: duplicate email",
        {"name":"Other","email":base_mail,"username":f"{base_user}_2","password":"password123","area":args.area}
    ))

    # 4) Bad email format (should error BAD_REQUEST)
    with_socket(lambda s: do_case(
        s, "BAD_REQUEST: bad email format",
        {"name":"BadEmail","email":"not-an-email","username":f"{base_user}_3","password":"password123","area":args.area}
    ))

    # 5) Bad username (too short / invalid chars) → BAD_REQUEST
    with_socket(lambda s: do_case(
        s, "BAD_REQUEST: bad username",
        {"name":"BadUser","email":f"baduser+{suf}@example.com","username":"ab","password":"password123","area":args.area}
    ))

    # 6) Bad password (too short) → BAD_REQUEST
    with_socket(lambda s: do_case(
        s, "BAD_REQUEST: short password",
        {"name":"BadPass","email":f"badpass+{suf}@example.com","username":f"{base_user}_4","password":"123","area":args.area}
    ))

    # 7) Missing field (e.g., area) → BAD_REQUEST
    with_socket(lambda s: do_case(
        s, "BAD_REQUEST: missing area",
        {"name":"NoArea","email":f"noarea+{suf}@example.com","username":f"{base_user}_5","password":"password123"}
    ))

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
