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
        time.sleep(0.05)  # tidy server logs

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=6000)
    ap.add_argument("--area", default="Hamra")
    args = ap.parse_args()

    # Unique IDs so the script is re-runnable
    suf = uuid.uuid4().hex[:6]
    username_ok = f"hayam_prof_sched_{suf}"
    email_ok = f"hayam.profile+{suf}@example.com"
    password_ok = "password123"

    # 0) PREP: register a user we’ll use for PROFILE + SCHEDULE
    def register_once(sock):
        payload = {
            "name": "Hayam",
            "email": email_ok,
            "username": username_ok,
            "password": password_ok,
            "area": args.area,
        }
        return do_case(sock, "PREP: register user", "AUTH.REGISTER_REQ", payload)

    with_socket(args.host, args.port, register_once)

    # 1) PROFILE + SCHEDULE sequence on a SINGLE persistent connection
    def profile_and_schedule_flow(sock):
        # 1.1) LOGIN (bind this TCP connection to user_id)
        do_case(sock, "LOGIN OK", "AUTH.LOGIN_REQ",
                {"username": username_ok, "password": password_ok})

        # 1.2) PROFILE.GET (self)
        do_case(sock, "PROFILE.GET (self)", "PROFILE.GET_REQ", {})

        # 1.3) PROFILE.SET first-time WITHOUT area (expect error only if your server requires area on first insert)
        # If your server already created 'users.area' during registration and allows insert without repassing area,
        # you may see success here — that’s okay. We test both paths.
        do_case(sock, "PROFILE.SET (missing area, expect error on first insert)",
                "PROFILE.SET_REQ",
                {
                    # intentionally omitting "area"
                    "is_driver": 0,
                    "vehicle": {"make": "Hyundai", "model": "i10", "color": "white", "plate": "B-123456"}
                })

        # 1.4) PROFILE.SET with area (should succeed)
        do_case(sock, "PROFILE.SET (with area, should succeed)",
                "PROFILE.SET_REQ",
                {
                    "area": args.area,
                    "is_driver": 0,
                    "vehicle": {"make": "Hyundai", "model": "i10", "color": "white", "plate": "B-123456"}
                })

        # 1.5) PROFILE.GET again (should reflect latest info)
        do_case(sock, "PROFILE.GET (self after set)", "PROFILE.GET_REQ", {})

        # 1.6) PROFILE.SET partial update (only vehicle plate) — should succeed (area remains unchanged)
        do_case(sock, "PROFILE.SET partial (only vehicle plate)",
                "PROFILE.SET_REQ",
                {
                    "vehicle": {"plate": "B-654321"}  # nothing else
                })

        # 1.7) SCHEDULE.SET while NOT driver (expect FORBIDDEN)
        do_case(sock, "SCHEDULE.SET (not driver yet, expect error)",
                "SCHEDULE.SET_REQ",
                {
                    "weekday": 1,
                    "depart_time": "07:30",
                    "direction": "to_AUB",
                    "area": args.area
                })

        # 1.8) PROFILE.SET enable driver mode
        do_case(sock, "PROFILE.SET (enable driver mode)",
                "PROFILE.SET_REQ",
                {
                    "is_driver": 1
                })

        # 1.9) SCHEDULE.SET valid #1
        res1 = do_case(sock, "SCHEDULE.SET (Mon 07:30 to_AUB)",
                "SCHEDULE.SET_REQ",
                {
                    "weekday": 1,
                    "depart_time": "07:30",
                    "direction": "to_AUB",
                    "area": args.area
                })

        # 1.10) SCHEDULE.SET valid #2
        res2 = do_case(sock, "SCHEDULE.SET (Wed 17:15 from_AUB)",
                "SCHEDULE.SET_REQ",
                {
                    "weekday": 3,
                    "depart_time": "17:15",
                    "direction": "from_AUB",
                    "area": args.area
                })

        # 1.11) SCHEDULE.LIST (all mine)
        do_case(sock, "SCHEDULE.LIST (all for me)", "SCHEDULE.LIST_REQ", {})

        # 1.12) SCHEDULE.LIST (filtered: to_AUB)
        do_case(sock, "SCHEDULE.LIST (filter direction to_AUB)",
                "SCHEDULE.LIST_REQ",
                {"direction": "to_AUB"})

        # 1.13) SCHEDULE.LIST (filtered: specific weekday)
        do_case(sock, "SCHEDULE.LIST (filter weekday=3)", "SCHEDULE.LIST_REQ", {"weekday": 3})

        # 1.14) SCHEDULE.SET invalid time
        do_case(sock, "SCHEDULE.SET (invalid HH:MM -> expect BAD_REQUEST)",
                "SCHEDULE.SET_REQ",
                {"weekday": 2, "depart_time": "7:3", "direction": "to_AUB", "area": args.area})

        # 1.15) SCHEDULE.SET invalid weekday
        do_case(sock, "SCHEDULE.SET (invalid weekday -> expect BAD_REQUEST)",
                "SCHEDULE.SET_REQ",
                {"weekday": 7, "depart_time": "08:00", "direction": "to_AUB", "area": args.area})

        # 1.16) Remove one schedule (if we got IDs)
        sid1 = (res1.get("payload") or {}).get("schedule_id")
        if isinstance(sid1, int):
            do_case(sock, "SCHEDULE.REMOVE (first schedule)",
                    "SCHEDULE.REMOVE_REQ", {"schedule_id": sid1})

        # 1.17) List again to confirm removal
        do_case(sock, "SCHEDULE.LIST (after removal)", "SCHEDULE.LIST_REQ", {})

        # 1.18) LOGOUT
        do_case(sock, "AUTH.LOGOUT", "AUTH.LOGOUT_REQ", {})

    with_socket(args.host, args.port, profile_and_schedule_flow)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
