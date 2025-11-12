# tests/test_for_acceptORcloseflow.py
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
from typing import Tuple

# ---------- repo root on sys.path ----------
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ---------- utilities: robust import without importlib.util ----------
def _try_import(name: str):
    try:
        return importlib.import_module(name)
    except Exception:
        return None

def _find_file(basename: str) -> pathlib.Path | None:
    # common locations first
    p = REPO_ROOT / basename
    if p.exists():
        return p
    for sub in ("server", "db", "src", "backend", "app"):
        q = REPO_ROOT / sub / basename
        if q.exists():
            return q
    # last resort deep search
    for q in REPO_ROOT.rglob(basename):
        return q
    return None

def _import_from_path(modname: str, path_obj: pathlib.Path | None):
    if not path_obj:
        return None
    g = runpy.run_path(str(path_obj))  # executes the file, returns globals dict
    mod = types.ModuleType(modname)
    mod.__dict__.update(g)
    sys.modules[modname] = mod
    return mod

def _purge_sqlite_dbs():
    """
    Remove likely sqlite files so db/database.py (which uses CREATE TABLE without
    IF NOT EXISTS) can run cleanly.
    """
    patterns = [
        "database.db",
        "*.sqlite",
        "*.sqlite3",
        "*_test.db",
        "db/*.db",
        "server/*.db",
    ]
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

def import_project_modules() -> Tuple[types.ModuleType, types.ModuleType]:
    """
    Import main.py (server) and database.py (schema) supporting:
      - package layout: server/main.py + db/database.py
      - flat layout: main.py + database.py
      - fallback: import by absolute path via runpy
    """
    # package layout
    m = _try_import("server.main"); d = _try_import("db.database")
    if m and d:
        return m, d
    # flat layout
    m = _try_import("main"); d = _try_import("database")
    if m and d:
        return m, d
    # fallback by path (ensure fresh DB before database.py runs)
    main_py = _find_file("main.py")
    db_py = _find_file("database.py")
    if db_py or main_py:
        _purge_sqlite_dbs()
    m = _import_from_path("project_main_by_path", main_py)
    d = _import_from_path("project_db_by_path", db_py)
    if m and d:
        return m, d
    raise RuntimeError("Could not import main.py and database.py (package, flat, or by path)")

# ---------- JSON-Lines socket helpers ----------
def send_msg(sock: socket.socket, mtype: str, payload: dict | None = None, mid: str | None = None):
    if mid is None:
        mid = str(uuid.uuid4())
    msg = {"type": mtype, "id": mid}
    if payload is not None:
        msg["payload"] = payload
    data = (json.dumps(msg) + "\n").encode("utf-8")
    sock.sendall(data)
    return mid

def read_line(sock: socket.socket, timeout: float = 8.0) -> dict:
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

def read_until(sock: socket.socket, want_types: set[str], timeout: float = 12.0) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        msg = read_line(sock, timeout=max(0.1, end - time.time()))
        if msg.get("type") in want_types:
            return msg
    raise TimeoutError(f"Did not receive one of {want_types} in time")

def new_client(host: str, port: int) -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host, port))
    return s

# ---------- protocol helpers ----------
def register_and_login(sock: socket.socket, name: str, username: str, email: str, password: str, area: str):
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

def set_driver(sock: socket.socket, area: str, vehicle: dict | None = None):
    payload = {"is_driver": True, "area": area}
    if vehicle:
        payload["vehicle"] = vehicle
    send_msg(sock, "PROFILE.SET_REQ", payload)
    res = read_until(sock, {"PROFILE.SET_RES", "ERROR"})
    assert res["type"] == "PROFILE.SET_RES", f"PROFILE.SET failed: {res}"

def add_schedule(sock: socket.socket, weekday: int, area: str, direction: str, depart_hhmm: str):
    send_msg(sock, "SCHEDULE.SET_REQ", {
        "weekday": weekday, "area": area,
        "direction": direction, "depart_time": depart_hhmm
    })
    res = read_until(sock, {"SCHEDULE.SET_RES", "ERROR"})
    assert res["type"] == "SCHEDULE.SET_RES", f"SCHEDULE.SET failed: {res}"

def make_request(sock: socket.socket, area: str, direction: str, time_iso: str) -> str:
    send_msg(sock, "RIDE.REQUEST_REQ", {
        "area": area, "direction": direction, "time_iso": time_iso
    })
    res = read_until(sock, {"RIDE.REQUEST_RES", "ERROR"})
    assert res["type"] == "RIDE.REQUEST_RES", f"RIDE.REQUEST failed: {res}"
    return res["payload"]["request_id"]

def accept_request(sock: socket.socket, request_id: str):
    send_msg(sock, "RIDE.ACCEPT_REQ", {"request_id": request_id})
    res = read_until(sock, {"RIDE.ACCEPT_RES", "ERROR"})
    assert res["type"] == "RIDE.ACCEPT_RES", f"RIDE.ACCEPT failed: {res}"

# ---------- weekday mapping identical to server ----------
def sun0_from_iso(iso_s: str) -> int:
    # Server computes weekday as (dt.weekday() + 1) % 7  → Sunday=0
    dt = datetime.fromisoformat(iso_s)
    return (dt.weekday() + 1) % 7

# ---------- server boot ----------
def start_server(host: str = "127.0.0.1", port: int = 6020):
    # ensure fresh DBs before any import that might CREATE TABLE
    _purge_sqlite_dbs()

    main_mod, db_mod = import_project_modules()

    # resolve DB path used by database.py
    db_file = getattr(db_mod, "DB_PATH", None) or getattr(db_mod, "DATABASE_PATH", None) or "database.db"
    db_path = (REPO_ROOT / db_file) if not os.path.isabs(db_file) else pathlib.Path(db_file)
    if db_path.exists():
        try:
            db_path.unlink()
        except Exception:
            pass

    # some schemas init on import; reload if possible
    try:
        importlib.reload(db_mod)
    except Exception:
        pass

    serve_fn = getattr(main_mod, "serve", None)
    if serve_fn is None:
        raise RuntimeError("Server module has no 'serve(host, port)' function")

    t = threading.Thread(target=serve_fn, args=(host, port), daemon=True)
    t.start()
    time.sleep(0.7)  # give listener time
    return host, port, db_path

# ---------- the test ----------
def test_match_flow():
    host, port, db_path = start_server()

    passenger = new_client(host, port)
    driver1 = new_client(host, port)
    driver2 = new_client(host, port)

    PW = "pass123"  # 6–20 chars per REGISTER validator

    register_and_login(passenger, "Passenger", "passenger", "p@example.com", PW, "Hamra")
    register_and_login(driver1, "Driver One", "driver1", "d1@example.com", PW, "Hamra")
    register_and_login(driver2, "Driver Two", "driver2", "d2@example.com", PW, "Hamra")

    # Make both drivers drivers and give them schedules that match the request time
    set_driver(driver1, "Hamra", {"make": "Toyota", "model": "Yaris", "color": "Blue", "plate": "B123"})
    set_driver(driver2, "Hamra", {"make": "Hyundai", "model": "i10", "color": "White", "plate": "C456"})

    REQ_TIME = "2025-11-12T08:32"  # a Wednesday
    W = sun0_from_iso(REQ_TIME)    # must be 3 for 2025-11-12, matching server logic

    add_schedule(driver1, weekday=W, area="Hamra", direction="to_AUB", depart_hhmm="08:30")
    add_schedule(driver2, weekday=W, area="Hamra", direction="to_AUB", depart_hhmm="08:35")

    # Passenger makes a request; immediately have Driver-1 accept by request_id
    req_id = make_request(passenger, "Hamra", "to_AUB", REQ_TIME)
    accept_request(driver1, req_id)

    # Passenger must receive RIDE.MATCHED with driver details
    p_msg = read_until(passenger, {"RIDE.MATCHED"})
    assert p_msg["payload"]["request_id"] == req_id
    assert "driver_info" in p_msg["payload"]
    assert "driver_ip" in p_msg["payload"]
    assert "driver_port" in p_msg["payload"]

    # Remaining driver must receive REQUEST.CLOSED
    d2_closed = read_until(driver2, {"REQUEST.CLOSED"})
    assert "winner_user_id" in d2_closed["payload"]

    # Database: request marked 'matched' + matches and ride_decision rows exist
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    req_int = int(req_id.split("_", 1)[1])

    cur.execute("SELECT status FROM ride_req WHERE request_id=?", (req_int,))
    row = cur.fetchone()
    assert row and row[0] == "matched", f"ride_req.status expected 'matched', got {row}"

    cur.execute("SELECT status FROM matches WHERE request_id=?", (req_int,))
    mrow = cur.fetchone()
    assert mrow and mrow[0] in ("active", "matched"), f"matches row missing or wrong status: {mrow}"

    cur.execute("SELECT status FROM ride_decision WHERE request_id=?", (req_int,))
    drow = cur.fetchone()
    assert drow and drow[0] in ("accepted", "accept"), f"ride_decision expected accepted/accept, got {drow}"

    con.close()

if __name__ == "__main__":
    try:
        test_match_flow()
        print("OK: match flow requirement satisfied.")
    except Exception as e:
        print(f"FAILED: {e}")
        raise
