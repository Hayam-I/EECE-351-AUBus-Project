# tests/test_p2p_bootstrap.py
import os
import sys
import json
import socket
import sqlite3
import threading
import time
import uuid
import importlib
import pathlib
import runpy
import types
from datetime import datetime

# ---------- repo root on sys.path ----------
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ---------- minimal, robust import (no importlib.util) ----------
def _try_import(name: str):
    try:
        return importlib.import_module(name)
    except Exception:
        return None

def _find_file(basename: str):
    p = REPO_ROOT / basename
    if p.exists():
        return p
    for sub in ("server", "db", "src", "backend", "app"):
        q = REPO_ROOT / sub / basename
        if q.exists():
            return q
    for q in REPO_ROOT.rglob(basename):
        return q
    return None

def _import_from_path(modname: str, path_obj: pathlib.Path | None):
    if not path_obj:
        return None
    g = runpy.run_path(str(path_obj))
    mod = types.ModuleType(modname)
    mod.__dict__.update(g)
    sys.modules[modname] = mod
    return mod

def _purge_sqlite_dbs():
    patterns = ["database.db", "*.sqlite", "*.sqlite3", "*_test.db", "db/*.db", "server/*.db"]
    for pat in patterns:
        for p in REPO_ROOT.glob(pat):
            try:
                p.unlink()
            except Exception:
                pass
    for p in REPO_ROOT.rglob("database.db"):
        try:
            p.unlink()
        except Exception:
            pass

def import_project_modules():
    m = _try_import("server.main"); d = _try_import("db.database")
    if m and d: return m, d
    m = _try_import("main"); d = _try_import("database")
    if m and d: return m, d
    main_py = _find_file("main.py"); db_py = _find_file("database.py")
    if db_py or main_py:
        _purge_sqlite_dbs()
    m = _import_from_path("project_main_by_path", main_py)
    d = _import_from_path("project_db_by_path", db_py)
    if m and d: return m, d
    raise RuntimeError("Could not import main.py and database.py")

# ---------- socket helpers (JSON Lines) ----------
def send_msg(sock, mtype, payload=None, mid=None):
    if mid is None:
        mid = str(uuid.uuid4())
    msg = {"type": mtype, "id": mid}
    if payload is not None:
        msg["payload"] = payload
    sock.sendall((json.dumps(msg) + "\n").encode("utf-8"))
    return mid

def read_line(sock, timeout=8.0):
    sock.settimeout(timeout)
    buf = b""
    while True:
        ch = sock.recv(1)
        if not ch:
            raise RuntimeError("socket closed")
        buf += ch
        if ch == b"\n":
            break
    return json.loads(buf.decode("utf-8"))

def read_until(sock, want_types, timeout=12.0):
    end = time.time() + timeout
    while time.time() < end:
        msg = read_line(sock, timeout=max(0.1, end - time.time()))
        if msg.get("type") in want_types:
            return msg
    raise TimeoutError(f"Did not receive one of {want_types} in time")

def new_client(host, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host, port))
    return s

# ---------- weekday mapping identical to server ----------
def sun0_from_iso(iso_s: str) -> int:
    dt = datetime.fromisoformat(iso_s)
    return (dt.weekday() + 1) % 7  # Sunday = 0

# ---------- protocol helpers ----------
def register_and_login(sock, name, username, email, password, area):
    send_msg(sock, "AUTH.REGISTER_REQ", {
        "name": name, "email": email, "username": username,
        "password": password, "area": area
    })
    reg_res = read_until(sock, {"AUTH.REGISTER_RES", "ERROR"})
    assert reg_res["type"] == "AUTH.REGISTER_RES", f"Register failed: {reg_res}"

    send_msg(sock, "AUTH.LOGIN_REQ", {"username": username, "password": password})
    login_res = read_until(sock, {"AUTH.LOGIN_RES", "ERROR"})
    assert login_res["type"] == "AUTH.LOGIN_RES", f"Login failed: {login_res}"
    return login_res["payload"]["user"]

def set_driver(sock, area, vehicle=None):
    payload = {"is_driver": True, "area": area}
    if vehicle:
        payload["vehicle"] = vehicle
    send_msg(sock, "PROFILE.SET_REQ", payload)
    res = read_until(sock, {"PROFILE.SET_RES", "ERROR"})
    assert res["type"] == "PROFILE.SET_RES", f"PROFILE.SET failed: {res}"

def add_schedule(sock, weekday, area, direction, depart_hhmm):
    send_msg(sock, "SCHEDULE.SET_REQ", {
        "weekday": weekday, "area": area,
        "direction": direction, "depart_time": depart_hhmm
    })
    res = read_until(sock, {"SCHEDULE.SET_RES", "ERROR"})
    assert res["type"] == "SCHEDULE.SET_RES", f"SCHEDULE.SET failed: {res}"

def make_request(sock, area, direction, time_iso):
    send_msg(sock, "RIDE.REQUEST_REQ", {
        "area": area, "direction": direction, "time_iso": time_iso
    })
    res = read_until(sock, {"RIDE.REQUEST_RES", "ERROR"})
    assert res["type"] == "RIDE.REQUEST_RES", f"RIDE.REQUEST failed: {res}"
    return res["payload"]["request_id"]

def accept_request(sock, request_id):
    send_msg(sock, "RIDE.ACCEPT_REQ", {"request_id": request_id})
    res = read_until(sock, {"RIDE.ACCEPT_RES", "ERROR"})
    assert res["type"] == "RIDE.ACCEPT_RES", f"RIDE.ACCEPT failed: {res}"

def peer_open(sock, p2p_port, ext_ip=None, ext_port=None):
    payload = {"p2p_port": p2p_port}
    if ext_ip and ext_port:
        payload["external_ip"] = ext_ip
        payload["external_port"] = ext_port
    send_msg(sock, "PEER.OPEN_REQ", payload)
    res = read_until(sock, {"PEER.OPEN_RES", "ERROR"})
    assert res["type"] == "PEER.OPEN_RES", f"PEER.OPEN failed: {res}"
    return res["payload"]["ip"], res["payload"]["port"]

# ---------- driver-side TCP listener (for pure P2P) ----------
class DriverListener:
    def __init__(self, host="0.0.0.0", port=55555):
        self.host = host
        self.port = port
        self._ls = None
        self.accepted_event = threading.Event()
        self.accepted_addr = None

    def start(self):
        self._ls = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._ls.bind((self.host, self.port))
        self._ls.listen(16)
        t = threading.Thread(target=self._accept_once, daemon=True)
        t.start()

    def _accept_once(self):
        try:
            conn, addr = self._ls.accept()
            self.accepted_addr = addr
            self.accepted_event.set()
            # we can close immediately; test only needs to prove reachability
            try:
                conn.close()
            except Exception:
                pass
        except Exception:
            pass

    def stop(self):
        try:
            if self._ls:
                self._ls.close()
        except Exception:
            pass

# ---------- server boot ----------
def start_server(host="127.0.0.1", port=6030):
    _purge_sqlite_dbs()
    main_mod, db_mod = import_project_modules()
    db_file = getattr(db_mod, "DB_PATH", None) or getattr(db_mod, "DATABASE_PATH", None) or "database.db"
    db_path = (REPO_ROOT / db_file) if not os.path.isabs(db_file) else pathlib.Path(db_file)
    if db_path.exists():
        try:
            db_path.unlink()
        except Exception:
            pass
    try:
        importlib.reload(db_mod)
    except Exception:
        pass
    serve_fn = getattr(main_mod, "serve", None)
    if serve_fn is None:
        raise RuntimeError("Server module has no 'serve(host, port)' function")
    t = threading.Thread(target=serve_fn, args=(host, port), daemon=True)
    t.start()
    time.sleep(0.7)
    return host, port, db_path

# ---------- the test ----------
def test_p2p_bootstrap():
    host, port, db_path = start_server()

    passenger = new_client(host, port)
    driver    = new_client(host, port)

    PW = "pass123"  # 6-20 chars per validator

    register_and_login(passenger, "Passenger", "passenger", "p@example.com", PW, "Hamra")
    register_and_login(driver,    "Driver",    "driver1",   "d1@example.com", PW, "Hamra")

    # Driver becomes a driver
    set_driver(driver, "Hamra", {"make":"Toyota","model":"Yaris","color":"Blue","plate":"B123"})

    # Driver opens a local TCP listener and announces it (PEER.OPEN_REQ)
    P2P_LOCAL_PORT = 55555
    listener = DriverListener(port=P2P_LOCAL_PORT)
    listener.start()
    # On localhost, external_ip/port not needed; server will use server-seen IP and provided port
    open_ip, open_port = peer_open(driver, P2P_LOCAL_PORT)

    # Add schedule that matches the request's weekday/time
    REQ_TIME = "2025-11-12T08:32"  # Wednesday
    W = sun0_from_iso(REQ_TIME)
    add_schedule(driver, weekday=W, area="Hamra", direction="to_AUB", depart_hhmm="08:30")

    # Passenger makes request; driver accepts
    req_id = make_request(passenger, "Hamra", "to_AUB", REQ_TIME)
    accept_request(driver, req_id)

    # Passenger receives RIDE.MATCHED (with driver_ip/driver_port)
    p_msg = read_until(passenger, {"RIDE.MATCHED"})
    assert p_msg["payload"]["request_id"] == req_id
    driver_ip   = p_msg["payload"]["driver_ip"]
    driver_port = p_msg["payload"]["driver_port"]
    assert isinstance(driver_ip, str) and isinstance(driver_port, int), f"Bad endpoint: {driver_ip}:{driver_port}"

    # PROVE pure TCP P2P reachability: passenger connects directly to driver ip:port
    s = socket.create_connection((driver_ip, driver_port), timeout=5.0)
    s.close()

    # Driver actually accepted the inbound P2P socket
    assert listener.accepted_event.wait(3.0), "Driver did not accept P2P connection"
    listener.stop()

    # DB assertions
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    req_int = int(req_id.split("_", 1)[1])

    cur.execute("SELECT status FROM ride_req WHERE request_id=?", (req_int,))
    row = cur.fetchone()
    assert row and row[0] == "matched", f"ride_req.status expected 'matched', got {row}"

    cur.execute("SELECT driver_ip, driver_port, status FROM matches WHERE request_id=?", (req_int,))
    mrow = cur.fetchone()
    assert mrow, "matches row missing"
    db_ip, db_port, mstatus = mrow
    assert db_ip == driver_ip and int(db_port) == int(driver_port), f"matches endpoint mismatch: {(db_ip, db_port)} != {(driver_ip, driver_port)}"
    assert mstatus in ("active", "matched"), f"unexpected matches.status: {mstatus}"

    con.close()

if __name__ == "__main__":
    try:
        test_p2p_bootstrap()
        print("OK: P2P bootstrap works — RIDE.MATCHED endpoint reachable, DB matched.")
    except Exception as e:
        print(f"FAILED: {e}")
        raise
