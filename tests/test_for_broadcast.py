#!/usr/bin/env python3
import socket, json, uuid, time, sys
from datetime import datetime, timedelta

HOST, PORT = "127.0.0.1", 6000
ENC = "utf-8"

def _uuid(): return str(uuid.uuid4())

def send_json(sock, obj):
    data = (json.dumps(obj, separators=(",", ":")) + "\n").encode(ENC)
    sock.sendall(data)

def recv_json(sock, timeout=4.0):
    sock.settimeout(timeout)
    buf = b""
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            raise RuntimeError("Socket closed")
        buf += chunk
        if b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            txt = line.decode(ENC, errors="replace").rstrip("\r").strip()
            return json.loads(txt)

class JsonlClient:
    def __init__(self):
        self.s = socket.create_connection((HOST, PORT), timeout=4.0)
        self.s.settimeout(4.0)
        self.user_preview = None

    def request(self, obj): 
        send_json(self.s, obj)
        return recv_json(self.s)

    def login_or_register(self, username, password, name, email, area):
        # Try register (ok if already exists)
        reg = {
            "type":"AUTH.REGISTER_REQ","id":_uuid(),
            "payload":{"name":name,"email":email,"username":username,"password":password,"area":area}
        }
        resp = self.request(reg)
        if resp.get("type") == "ERROR":
            # accept already-taken errors; anything else is fatal
            code = (resp.get("payload") or {}).get("code", "")
            if code not in ("AUTH_USERNAME_TAKEN","AUTH_EMAIL_TAKEN"):
                raise RuntimeError(f"Register failed: {resp}")

        # Login
        login = {"type":"AUTH.LOGIN_REQ","id":_uuid(),"payload":{"username":username,"password":password}}
        resp = self.request(login)
        assert resp.get("type") == "AUTH.LOGIN_RES", f"Login failed: {resp}"
        self.user_preview = resp["payload"]["user"]
        return self.user_preview

    def set_profile(self, *, is_driver=None, area=None, name=None, email=None):
        payload = {}
        if is_driver is not None: payload["is_driver"] = bool(is_driver)
        if area is not None: payload["area"] = area
        if name is not None: payload["name"] = name
        if email is not None: payload["email"] = email
        resp = self.request({"type":"PROFILE.SET_REQ","id":_uuid(),"payload":payload})
        assert resp.get("type") == "PROFILE.SET_RES", f"Profile set failed: {resp}"
        return True

    def add_schedule(self, weekday, hhmm, direction, area):
        payload = {"weekday":weekday,"depart_time":hhmm,"direction":direction,"area":area}
        resp = self.request({"type":"SCHEDULE.SET_REQ","id":_uuid(),"payload":payload})
        return resp

    def list_schedule(self):
        resp = self.request({"type":"SCHEDULE.LIST_REQ","id":_uuid(),"payload":{}})
        assert resp.get("type") == "SCHEDULE.LIST_RES", f"List schedules failed: {resp}"
        return resp["payload"]["items"]

    def remove_schedule(self, schedule_id:int):
        resp = self.request({"type":"SCHEDULE.REMOVE_REQ","id":_uuid(),"payload":{"schedule_id":schedule_id}})
        return resp

    def ride_request(self, *, area, direction, time_iso):
        # Your teammate added RIDE.REQUEST_REQ -> ride_request_new
        resp = self.request({"type":"RIDE.REQUEST_REQ","id":_uuid(),
                             "payload":{"area":area,"direction":direction,"time_iso":time_iso}})
        return resp

    def recv_any(self, timeout=4.0):
        return recv_json(self.s, timeout=timeout)

def next_weekday_sun0(target_sun0: int, hhmm: str) -> datetime:
    """Return a datetime in the future on weekday (Sun=0..Sat=6) at HH:MM local time."""
    now = datetime.now()
    today_sun0 = (now.weekday() + 1) % 7
    delta = (target_sun0 - today_sun0) % 7
    if delta == 0:
        # same day: if time has passed, push to next week
        hh, mm = map(int, hhmm.split(":"))
        candidate = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if candidate <= now:
            delta = 7
    target_date = now + timedelta(days=delta)
    hh, mm = map(int, hhmm.split(":"))
    return target_date.replace(hour=hh, minute=mm, second=0, microsecond=0)

def main():
    print("Connecting driver and passenger clients…")
    driver = JsonlClient()
    passenger = JsonlClient()

    # 1) Accounts + login
    driver.login_or_register("driver1", "pass123", "Driver One", "driver1@example.com", "Hamra")
    passenger.login_or_register("pass1", "pass123", "Passenger One", "pass1@example.com", "Hamra")

    # 2) Driver mode ON (puts driver socket into ONLINE_DRIVERS on server)
    driver.set_profile(is_driver=True, area="Hamra")

    # 3) Add schedule (and verify duplicate rejection)
    # Choose a weekday/time that we'll also use for the passenger ride request.
    wk = 1  # Mon (Sun=0)
    hhmm = "09:00"
    direction = "from_AUB"
    area = "Hamra"

    print("Adding schedule once…")
    r1 = driver.add_schedule(wk, hhmm, direction, area)
    assert r1.get("type") == "SCHEDULE.SET_RES", f"Expected SET_RES, got: {r1}"

    print("Adding SAME schedule again (should be duplicate)…")
    r2 = driver.add_schedule(wk, hhmm, direction, area)
    assert r2.get("type") == "ERROR", f"Expected ERROR on duplicate, got: {r2}"
    assert (r2.get("payload") or {}).get("code") in ("SCHEDULE_DUPLICATE","BAD_REQUEST"), f"Unexpected duplicate code: {r2}"

    # 4) List schedules and remember the schedule_id to test deletion later
    print("Listing schedules…")
    items = driver.list_schedule()
    assert any(it["weekday"] == wk and it["depart_time"] == hhmm and it["direction"] == direction and it["area"] == area for it in items), "Schedule not found in list."
    sched_id = next(it["schedule_id"] for it in items if it["weekday"] == wk and it["depart_time"] == hhmm and it["direction"] == direction and it["area"] == area)

    # 5) Ride request by passenger at ~09:05 (within ±30m of driver)
    ride_dt = next_weekday_sun0(wk, "09:05")
    # Your server expects an ISO string. Use 'YYYY-MM-DD HH:MM' (or 'T' separator).
    time_iso = ride_dt.strftime("%Y-%m-%d %H:%M")

    print("Posting ride request…")
    rr = passenger.ride_request(area=area, direction=direction, time_iso=time_iso)
    if rr.get("type") == "ERROR":
        print("\n⚠ Ride request returned ERROR. Details:", rr, "\n")
        print("Likely cause: your server’s _minutes_from_iso currently uses datetime.fromtimestamp on a string.")
        print("Fix it to use datetime.fromisoformat(iso_s.replace(' ', 'T')) and recompute weekday as Sun=0.\n")
    else:
        assert rr.get("type") == "RIDE.REQUEST_RES", f"Unexpected ride response: {rr}"
        print("Ride request created:", rr["payload"])
        # 6) Driver should receive DRIVER.BROADCAST
        print("Waiting for DRIVER.BROADCAST on driver socket…")
        msg = driver.recv_any(timeout=4.0)
        assert msg.get("type") == "DRIVER.BROADCAST", f"Expected DRIVER.BROADCAST, got: {msg}"
        pl = msg.get("payload") or {}
        assert "request_id" in pl and "passenger_preview" in pl, "Broadcast payload incomplete."
        print("Driver received broadcast ✔")

    # 7) Delete schedule and confirm disappearance
    print("Deleting schedule…")
    rd = driver.remove_schedule(sched_id)
    assert rd.get("type") == "SCHEDULE.REMOVE_RES", f"Remove failed: {rd}"

    items2 = driver.list_schedule()
    assert not any(it["schedule_id"] == sched_id for it in items2), "Schedule still present after delete."

    print("\n All basic tests passed.")
    driver.s.close(); passenger.s.close()

if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"\n Test assertion failed:\n{e}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n Test crashed:\n{e}\n")
        sys.exit(2)
