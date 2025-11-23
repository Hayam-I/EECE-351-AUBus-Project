#!/usr/bin/env python3
"""
AUBus – Server
-------------------------------------------
Transport: TCP + JSON Lines (one connection per client)

Envelope (all messages):
  { "type": "<MessageType>", "id": "<UUIDv4>", "payload": {...}? }

Auth model (per-connection):
  • After AUTH.LOGIN_RES, we bind THIS TCP connection to that user_id.
  • PROFILE.SET/GET require the connection to be logged in.

Supported:
  CONTROL: PING -> PONG
  AUTH:    REGISTER_REQ/RES, LOGIN_REQ/RES, LOGOUT_REQ/RES
  PROFILE: SET_REQ/RES, GET_REQ/RES
  SCHEDULE: SET_REQ/RES, LIST_REQ/RES, REMOVE_REQ/RES
  ! NOT UP TO DATE, I HAVE ADDED RIDE:
  
  
N.B TO SELF: password is plaintext, consider TLS, later not rn
N.B 2:  A driver can only accept 1 passenger and  i added helpers to free driver but req/res is not implemented (under: #FREEING THE DRIVER LATER)

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
from collections import defaultdict
import time
from datetime import datetime


# ---------------------------
# Constants and configuration
# ---------------------------
ENCODING = "utf-8"
BACKLOG = 10
RECV_BUFSIZE = 4096
DB_PATH = "database.db"

#----------------------------
# mapping:
# driver_user_id -> driver socket
# request_id ->set(driver_user_id)
# request_id -> last activity ts
# map request -> passenger and driver -> ip, port so request_id -> {user_id, socket}, driver_user_id -> ip, port
#----------------------------

"""
a single request once one driver accepts it, but theres nothing that prevents that same driver from accepting another request later (or concurrently) because we dont keep any “driver is busy” state in memory or in the DB.
"""
BUSY_DRIVERS: set[int] = set()
ONLINE_DRIVERS: dict[int, socket.socket] = {}
ACTIVE_REQUEST_DRIVERS: dict[str, set[int]] = defaultdict(set)
_REQUEST_LAST_TOUCH: dict[str, float] =  {}
REQUEST_TTL_SECONDS = 120

REQUEST_PASSENGERS: dict[str, dict] = {}
DRIVER_PEERS: dict[int, tuple[str,int]] = {}

STATE_LOCK = threading.Lock()



from math import radians, sin, cos, asin, sqrt

def haversine_km(lat1, lon1, lat2, lon2):
    # convert degrees to radians
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    R = 6371.0  # Earth radius in km
    return R * c



# ---------------------------
# UUIDv4 validation/helpers
# ---------------------------
def is_valid_uuid4(value: str) -> bool:
    if not isinstance(value, str):
        return False
    try:
        u = uuid.UUID(value, version=4)
    except (ValueError, TypeError):
        return False
    return str(u) in (value, value.lower(), value.upper())

def _uuid() -> str:
    return str(uuid.uuid4())

# ---------------------------------------------------------
# JSON-L helpers
# ---------------------------------------------------------
def recv_lines(sock: socket.socket):
    buf = b""
    while True:
        chunk = sock.recv(RECV_BUFSIZE)
        if not chunk:
            return
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            yield line.decode(ENCODING, errors="replace").rstrip("\r").strip()

def send_json(sock: socket.socket, obj: dict):
    data = (json.dumps(obj, separators=(",", ":")) + "\n").encode(ENCODING)
    sock.sendall(data)

def _send_json_safe(sock: socket.socket, obj: dict):
    try:
        send_json(sock, obj)
    except Exception:
        logging.exception("send failed")


# ---------------------------------------------------------
# Validation helpers (time/registration/login/schedule/requests)
# ---------------------------------------------------------
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,20}$")
PASSWORD_RE = re.compile(r"^.{6,20}$")
EMAIL_RE    = re.compile(r"^[^@]+@[^@]+\.[^@]+$")

TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")  # HH:MM 24h

def validate_register_payload(p: dict):
    missing = [k for k in ("name", "email", "username", "password", "area") if k not in p]
    if missing:
        return False, f"Missing fields: {', '.join(missing)}"
    if not USERNAME_RE.match(p["username"]):
        return False, "Invalid username (5-20 letters/digits/underscores)"
    if not PASSWORD_RE.match(p["password"]):
        return False, "Invalid password (6-20 characters)"
    if not EMAIL_RE.match(p["email"]):
        return False, "Invalid email format"
    if not isinstance(p["area"], str) or not p["area"]:
        return False, "Area must be a non-empty string"
    return True, ""

def validate_schedule_payload(p):
    missing = [k for k in ("weekday", "depart_time", "direction", "area") if k not in p]
    if missing:
        return False, f"Missing fields: {', '.join(missing)}"
    wd = p["weekday"]
    if not isinstance(wd, int) or not (0 <= wd <= 6):
        return False, "weekday must be int in 0..6"
    if not isinstance(p["area"], str) or not p["area"]:
        return False, "area must be a non-empty string"
    # FIX: the original had TIME_RE.match(p["depart_time"], str) which is invalid
    if not isinstance(p["depart_time"], str) or not TIME_RE.match(p["depart_time"]):
        return False, "depart_time must be 'HH:MM' (24h)"
    # Consistency: choose ONE vocabulary and keep it everywhere (DB/validators/clients)
    if p["direction"] not in ("to_AUB", "from_AUB"):
        return False, "direction must be 'to_AUB' or 'from_AUB'"
    return True, ""


def require_logged_in(conn_state, mid):
    uid = conn_state.get("user_id")
    if not uid:
        return None, {"type": "ERROR", "id": mid,
                      "payload": {"code": "FORBIDDEN", "message": "Login required"}}
    return uid, None

def require_driver(conn_state, mid):
    try:
        conn = sqlite3.connect(DB_PATH)
        cur  = conn.cursor()
        cur.execute("SELECT is_driver FROM users WHERE user_id=?", (conn_state.get("user_id"),))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None, {"type": "ERROR", "id": mid,
                          "payload": {"code": "NOT_FOUND", "message": "User not found."}}
        if int(row[0]) != 1:
            return None, {"type": "ERROR", "id": mid,
                          "payload": {"code": "FORBIDDEN", "message": "Driver mode must be on."}}
        return True, None
    except Exception:
        logging.exception("require_driver failed")
        return None, {"type": "ERROR", "id": mid,
                      "payload": {"code": "SERVER_ERROR", "message": "Internal error"}}

#time/location helpers
def _minutes_from_hhmm(s: str) -> int:
    hh, mm = s.split(":")
    return int(hh) * 60 + int(mm)

def _minutes_from_iso(iso_s: str) -> tuple[int, int]:
    dt = datetime.fromisoformat(iso_s.replace(" ", "T"))
    py_wd = dt.weekday()
    sun0 = (py_wd + 1) % 7
    minutes = dt.hour * 60 + dt.minute
    return sun0, minutes

def _now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"

#going from req_123 -> 123
def _reqid_to_int(req_id: str) -> int | None:
    if isinstance(req_id, str) and req_id.startswith("req_"):
        try:
            return int(req_id.split("_",1)[1])
        except ValueError:
            return None
    return None

def _normalize_peer_endpoint(conn_state: dict, announced_port: int | None) -> tuple[str | None, int | None]:
    """
     Choose the best (ip, port) we can give to the passenger for P2P bootstrap.
    - IP is always the server-observed remote IP from this TCP connection.
    - Port is driver's explicitly announced P2P port if valid, else None.
    """
    ip = None
    port = None
    try:
        if isinstance(conn_state.get("peer"), tuple):
            ip = conn_state["peer"][0]
        if isinstance(announced_port, int) and 1 <= announced_port <= 65535:
            port = announced_port
    except Exception:
        pass
    return ip, port


# ---------------------------------------------------------
# DB utilities
# ---------------------------------------------------------
def register_user(p: dict):
    ok, msg = validate_register_payload(p)
    if not ok:
        return False, {"code": "BAD_REQUEST", "message": msg}
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO users (name, username, password, email, is_driver, area) "
                "VALUES (?, ?, ?, ?, 0, ?)",
                (p["name"], p["username"], p["password"], p["email"], p["area"]),
            )
            conn.commit()
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

def _user_preview_from_row(row):
    # row = (user_id, name, username, password, email, is_driver, area, rating_sum, rating_avg, rating_count)
    return {
        "user_id": f"user_{row[0]}",
        "name": row[1],
        "username": row[2],
        "email": row[4],
        "is_driver": bool(row[5]),
        "area": row[6],
        "rating_sum": row[7],
        "rating_avg": float(row[8]) if row[8] is not None else 0.0,
        "rating_count": row[9],
    }
#fter a successful AUTH.LOGIN_REQ, the server stores user_id in the per-socket state; subsequent messages on that same TCP connection are considered “logged in”.
def login_user(p: dict):
    for k in ("username", "password"):
        if k not in p or not isinstance(p[k], str) or not p[k]:
            return False, {"code": "BAD_REQUEST", "message": f"Missing/invalid field: {k}"}
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
    "SELECT user_id, name, username, password, email, is_driver, area, rating_sum, rating_avg, rating_count "
    "FROM users WHERE username=?",
    (p["username"],),
)
        row = cur.fetchone()
        if not row or row[3] != p["password"]:
            return False, {"code": "AUTH_INVALID_CREDENTIALS", "message": "Invalid username or password"}
        return True, {"user": _user_preview_from_row(row), "user_id_int": int(row[0])}
    finally:
        conn.close()

# ---------------------------------------------------------
# PROFILE handlers (connection must be logged in)
# ---------------------------------------------------------
def profile_set(user_id: int, payload: dict, mid):
    if not user_id:
        return {"type": "ERROR", "id": mid, "payload": {"code": "FORBIDDEN", "message": "Login required"}}

    p = payload or {}
    name      = p.get("name")
    email     = p.get("email")
    area_in   = p.get("area")              # may be None on partial update
    is_driver = 1 if p.get("is_driver") else 0
    vehicle   = p.get("vehicle") or {}
    v_make  = vehicle.get("make")
    v_model = vehicle.get("model")
    v_color = vehicle.get("color")
    v_plate = vehicle.get("plate")

    try:
        conn = sqlite3.connect(DB_PATH)
        cur  = conn.cursor()

        # Do we already have a profile?
        cur.execute("SELECT user_id, area FROM profiles WHERE user_id=?", (user_id,))
        prof = cur.fetchone()

        # Also read current users.area to allow fallback if profile is missing
        cur.execute("SELECT area FROM users WHERE user_id=?", (user_id,))
        urow = cur.fetchone()
        user_area = urow[0] if urow else None

        if prof is None:
            # First-time profile creation: area is mandatory (from payload or users.area)
            new_area = area_in if (isinstance(area_in, str) and area_in.strip()) else user_area
            if not isinstance(new_area, str) or not new_area.strip():
                conn.close()
                return {"type":"ERROR","id":mid,
                        "payload":{"code":"PROFILE_AREA_REQUIRED","message":"area is required for first-time profile"}}

            # Update main user record (COALESCE preserves existing when None)
            cur.execute(
                "UPDATE users SET name=COALESCE(?,name), email=COALESCE(?,email), area=? , is_driver=? WHERE user_id=?",
                (name, email, new_area, is_driver, user_id),
            )

            # Insert profile
            cur.execute(
                "INSERT INTO profiles (user_id, is_driver, area, vehicle_make, vehicle_model, vehicle_color, vehicle_plate)"
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, is_driver, new_area, v_make, v_model, v_color, v_plate),
            )
        else:
            # Subsequent edits: only overwrite area if provided; otherwise keep existing profile area
            current_area = prof[1]
            new_area = area_in if (isinstance(area_in, str) and area_in.strip()) else current_area

            # Update users + profiles
            cur.execute(
                "UPDATE users SET name=COALESCE(?,name), email=COALESCE(?,email), area=?, is_driver=? WHERE user_id=?",
                (name, email, new_area, is_driver, user_id),
            )
            cur.execute(
                "UPDATE profiles SET is_driver=?, area=?, vehicle_make=?, vehicle_model=?, vehicle_color=?, vehicle_plate=?"
                "WHERE user_id=?",
                (is_driver, new_area, v_make, v_model, v_color, v_plate, user_id),
            )

        conn.commit()
        conn.close()
        return {"type": "PROFILE.SET_RES", "id": mid, "payload": {}}

    except Exception:
        logging.exception("profile_set failed")
        return {"type": "ERROR", "id": mid,
                "payload": {"code": "SERVER_ERROR", "message": "Failed to update profile"}}

def profile_get(current_user_id: int, payload: dict, mid):
    # If payload contains user_id like "user_7" we'll read that; otherwise default to current connection user.
    p = payload or {}
    target_uid = None
    if isinstance(p.get("user_id"), str) and p["user_id"].startswith("user_"):
        try:
            target_uid = int(p["user_id"].split("_", 1)[1])
        except ValueError:
            return {"type": "ERROR", "id": mid, "payload": {"code": "BAD_REQUEST", "message": "Invalid user_id format"}}
    else:
        target_uid = current_user_id

    if not target_uid:
        return {"type": "ERROR", "id": mid, "payload": {"code": "FORBIDDEN", "message": "Login required or provide user_id"}}

    try:
        conn = sqlite3.connect(DB_PATH)
        cur  = conn.cursor()
        cur.execute(
            "SELECT user_id,name,username,password,email,is_driver,area,rating_sum,rating_avg,rating_count "
            "FROM users WHERE user_id=?",
            (target_uid,),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return {"type": "ERROR", "id": mid, "payload": {"code": "NOT_FOUND", "message": "User not found"}}
        user = {
            "user_id": f"user_{row[0]}",
            "name": row[1],
            "area": row[6],
            "is_driver": bool(row[5]),
            "rating_avg": row[8],
            "rating_count": row[9],
        }
        return {"type": "PROFILE.GET_RES", "id": mid, "payload": {"user": user}}
    except Exception:
        logging.exception("profile_get failed")
        return {"type": "ERROR", "id": mid, "payload": {"code": "SERVER_ERROR", "message": "Internal error"}}

#---------------------------------------------------------
# Scheduele handlers (connection must be logged in)
# ---------------------------------------------------------
def schedule_set(conn_state, payload, mid):
    uid, err = require_logged_in(conn_state, mid)
    if err:
        return err
    _ok, derr = require_driver(conn_state, mid)
    if derr:
        return derr

    ok, msg = validate_schedule_payload(payload or {})
    if not ok:
        return {"type": "ERROR", "id": mid, "payload": {"code": "BAD_REQUEST", "message": msg}}

    p = payload or {}
    lat = p.get("lat")
    lon = p.get("lon")

    # Require coords for matching
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return {
            "type": "ERROR",
            "id": mid,
            "payload": {"code": "BAD_REQUEST", "message": "lat and lon must be numeric"},
        }

    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        cur.execute("BEGIN IMMEDIATE")
        cur.execute(
            """
            SELECT 1 FROM schedules
            WHERE user_id=? AND weekday=? AND depart_time=? AND direction=? AND area=?
            LIMIT 1
            """,
            (uid, p["weekday"], p["depart_time"], p["direction"], p["area"]),
        )
        if cur.fetchone():
            conn.rollback()
            conn.close()
            return {
                "type": "ERROR",
                "id": mid,
                "payload": {
                    "code": "SCHEDULE_DUPLICATE",
                    "message": "This exact schedule already exists",
                },
            }

        cur.execute(
            """
            INSERT INTO schedules (user_id, weekday, depart_time, direction, area, lat, lon)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (uid, p["weekday"], p["depart_time"], p["direction"], p["area"], lat, lon),
        )
        schedule_id = cur.lastrowid
        conn.commit()
        conn.close()
        return {"type": "SCHEDULE.SET_RES", "id": mid, "payload": {"schedule_id": schedule_id}}
    except Exception:
        logging.exception("schedule_set failed")
        return {
            "type": "ERROR",
            "id": mid,
            "payload": {"code": "SERVER_ERROR", "message": "Failed to set schedule"},
        }


def schedule_get(conn_state, payload, mid):
    uid, err = require_logged_in(conn_state, mid)
    if err: return err
    
    p = payload or {}
    weekday   = p.get("weekday")
    direction = p.get("direction")
    area      = p.get("area")

    clauses = ["user_id=?"]
    args = [uid]
    if isinstance(weekday, int):
        clauses.append("weekday=?");   args.append(weekday)
    if isinstance(area, str) and area:
        clauses.append("area=?");      args.append(area)
    if direction in ("to_AUB", "from_AUB"):
        clauses.append("direction=?"); args.append(direction)

    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()  # <-- FIX
        q = "SELECT schedule_id, weekday, depart_time, direction, area FROM schedules WHERE " \
            + " AND ".join(clauses) + " ORDER BY weekday, depart_time"
        cur.execute(q, tuple(args))
        items = [
            {"schedule_id": r[0], "weekday": r[1], "depart_time": r[2], "direction": r[3], "area": r[4]}
            for r in cur.fetchall()
        ]
        conn.close()
        return {"type": "SCHEDULE.LIST_RES", "id": mid, "payload": {"items": items}}
    except Exception:
        logging.exception("schedule_list")
        return {"type": "ERROR", "id": mid, "payload": {"code": "SERVER_ERROR", "message": "Failed to list schedules"}}

def schedule_remove(conn_state, payload, mid):
    uid, err = require_logged_in(conn_state, mid)
    if err: return err
    _ok, derr = require_driver(conn_state, mid)
    if derr: return derr

    p = payload or {}
    sid = p.get("schedule_id")
    if not isinstance(sid, int):
        return {"type":"ERROR","id":mid,"payload":{"code":"BAD_REQUEST","message":"schedule_id (int) required"}}
    try:
        conn = sqlite3.connect(DB_PATH)
        cur  = conn.cursor()
        cur.execute("DELETE FROM schedules WHERE schedule_id=? AND user_id=?", (sid, uid))
        deleted = cur.rowcount
        conn.commit(); conn.close()
        if deleted == 0:
            return {"type":"ERROR","id":mid,"payload":{"code":"NOT_FOUND","message":"Schedule not found or not yours"}}
        return {"type":"SCHEDULE.REMOVE_RES","id":mid,"payload":{}}
    except Exception:
        logging.exception("schedule_remove")
        return {"type":"ERROR","id":mid,"payload":{"code":"SERVER_ERROR","message":"Failed to remove schedule"}}         

#---------------
#ride
#--------------
def _gc_requests():
    now = time.time()
    with STATE_LOCK:
        for req_id, ts in list(_REQUEST_LAST_TOUCH.items()):
            if now - ts > REQUEST_TTL_SECONDS:
                ACTIVE_REQUEST_DRIVERS.pop(req_id, None)
                _REQUEST_LAST_TOUCH.pop(req_id, None)
                REQUEST_PASSENGERS.pop(req_id, None)

def _driver_info_preview(uid: int):
    """
    Build a small driver card for RIDE.MATCHED.
    Robust to either:
      - profiles table with vehicle_make/model/color/plate columns, or
      - profiles table with a single 'vehicle' JSON/text column, or
      - no vehicle info at all.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        # ---- Basic driver info (fix missing space before FROM) ----
        cur.execute(
            "SELECT user_id, name, username, email, is_driver, area, rating_sum, rating_avg, rating_count "
            "FROM users WHERE user_id=?",
            (uid,),
        )
        u = cur.fetchone()
        if not u:
            conn.close()
            return None

        (user_id, name, username, email, is_driver, area,
         rating_sum, rating_avg, rating_count) = u

        # ---- Detect profiles schema ----
        cur.execute("PRAGMA table_info(profiles)")
        cols = {row[1] for row in cur.fetchall()}

        vehicle = None
        if {"vehicle_make", "vehicle_model", "vehicle_color", "vehicle_plate"} <= cols:
            # Column-per-attribute layout
            cur.execute(
                "SELECT vehicle_make, vehicle_model, vehicle_color, vehicle_plate "
                "FROM profiles WHERE user_id=?",
                (uid,),
            )
            prow = cur.fetchone()
            if prow:
                vehicle = {
                    "make": prow[0],
                    "model": prow[1],
                    "color": prow[2],
                    "plate": prow[3],
                }
        elif "vehicle" in cols:
            # Single JSON/text column layout
            cur.execute(
                "SELECT vehicle FROM profiles WHERE user_id=?",
                (uid,),
            )
            prow = cur.fetchone()
            if prow and prow[0]:
                try:
                    import json
                    v = prow[0]
                    vehicle = json.loads(v) if isinstance(v, str) else v
                except Exception:
                    vehicle = None  # keep graceful if parse fails

        conn.close()

        return {
            "user_id": f"user_{user_id}",
            "name": name,
            "username": username,
            "email": email,
            "is_driver": bool(is_driver),
            "area": area,
            "rating_sum": rating_sum,
            "rating_avg": float(rating_avg) if rating_avg is not None else 0.0,
            "rating_count": rating_count,
            "vehicle": vehicle,
        }
    except Exception:
        logging.exception("_driver_info_preview failed")
        try:
            conn.close()
        except Exception:
            pass
        return None


def _broadcast_driver_candidates(request_id: str, passenger_preview: dict, candidate_user_ids: list[int]):
    now = time.time()
    sent = 0
    targets: list[tuple[socket.socket, dict]] = []

    with STATE_LOCK:
        ACTIVE_REQUEST_DRIVERS.setdefault(request_id, set())
        for uid in candidate_user_ids:
            if uid in BUSY_DRIVERS or _driver_has_active_match(uid):
                continue
            sock = ONLINE_DRIVERS.get(uid)
            if not sock:
                continue
            ACTIVE_REQUEST_DRIVERS[request_id].add(uid)
            # stash target to send outside the lock
            targets.append((sock, {
                "type": "DRIVER.BROADCAST",
                "id": _uuid(),
                "payload": {
                    "request_id": request_id,
                    "passenger_preview": passenger_preview,
                },
            }))
            sent += 1
        _REQUEST_LAST_TOUCH[request_id] = now

    # Do network I/O without holding the lock
    for sock, msg in targets:
        _send_json_safe(sock, msg)

    return sent


def _notify_request_closed(request_id: str, winner_uid: int, remaining: set[int]):
    targets = []
    with STATE_LOCK:
        for uid in list(remaining):
            sock = ONLINE_DRIVERS.get(uid)
            if sock:
                targets.append(sock)

    for sock in targets:
        _send_json_safe(sock, {
            "type": "REQUEST.CLOSED",
            "id": _uuid(),
            "payload": {
                "request_id": request_id,
                "winner_user_id": f"user_{winner_uid}",
            },
        })

def _driver_has_active_match(driver_id: int) -> bool:
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM matches WHERE driver_id=? AND status='active' LIMIT 1", (driver_id,))
        row = cur.fetchone()
        conn.close()
        return bool(row)
    except Exception:
        logging.exception("_driver_has_active_match failed")
        return True
        

def _ride_accept(conn_state, payload, mid):
    driver_id, err = require_logged_in(conn_state, mid)
    if err:
        return err
    _ok, derr = require_driver(conn_state, mid)
    if derr:
        return derr

    req_s = (payload or {}).get("request_id")
    req_id_int = _reqid_to_int(req_s)
    if not isinstance(req_id_int, int):
        return {"type":"ERROR", "id":mid, "payload":{
            "code":"BAD_REQUEST",
            "message":"invalid request_id"
        }}
    with STATE_LOCK:
        busy_now = driver_id in BUSY_DRIVERS

    if busy_now or _driver_has_active_match(driver_id):
        return {"type":"ERROR", "id":mid, "payload":{
            "code":"DRIVER_BUSY",
            "message":"Driver already has an active match"
        }}
    
    if time.time() - _REQUEST_LAST_TOUCH.get(f"req_{req_id_int}", 0) > REQUEST_TTL_SECONDS:
        return {"type":"ERROR","id":mid,"payload":{"code":"REQUEST_EXPIRED","message":"request expired"}}
    

    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        # 1) Ensure request exists and is open
        cur.execute("SELECT user_id, area, direction, departure_time, status FROM ride_req WHERE request_id=?",
                    (req_id_int,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return {"type":"ERROR", "id":mid, "payload":{
                "code":"NOT_FOUND",
                "message":"request not found"
            }}
        passenger_id, area, direction, departure_time, req_status = row
        if req_status != "open":
            conn.close()
            return {"type":"ERROR", "id":mid, "payload":{
                "code":"REQUEST_CLOSED",
                "message":"request not open"
            }}
        
        if driver_id == passenger_id:
            return {"type":"ERROR","id":mid,"payload":{"code":"BAD_REQUEST","message":"cannot accept your own request"}}


        # 2) Resolve driver's reachable endpoint from DRIVER_PEERS
        with STATE_LOCK:
            driver_ip, driver_port = DRIVER_PEERS.get(driver_id, (None, None))
        if driver_ip is None or driver_port is None:
            return {"type":"ERROR","id":mid,"payload":{"code":"BAD_REQUEST","message":"driver P2P endpoint unknown"}}

        if driver_id not in ACTIVE_REQUEST_DRIVERS.get(f"req_{req_id_int}", set()):
            return {"type":"ERROR","id":mid,"payload":{"code":"FORBIDDEN","message":"not eligible for this request"}}

        # 3) Insert match row and mark request matched (transactionally)
        cur.execute("""
            INSERT INTO matches(
                request_id, user_id, driver_id, area, direction, departure_time,
                driver_ip, driver_port, user_ip, user_port, status, created_at, accepted_at
            )
            VALUES(?,?,?,?,?,?,?,?,?,?, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (req_id_int, passenger_id, driver_id, area, direction, departure_time,
              driver_ip, driver_port, None, None))

        # Optional: record acceptance in ride_decision if your schema expects it
        try:
            cur.execute("""
                INSERT INTO ride_decision(request_id, user_id, driver_id, status, decided_at)
                VALUES(?, ?, ?, 'accepted', CURRENT_TIMESTAMP)
            """, (req_id_int, passenger_id, driver_id))
        except Exception:
            # If table doesn't exist or is optional, keep going
            pass

        cur.execute("UPDATE ride_req SET status='matched' WHERE request_id=? AND status='open'",
                    (req_id_int,))
        if cur.rowcount == 0:
            conn.rollback()
            conn.close()
            return {"type":"ERROR","id":mid,"payload":{
                "code":"REQUEST_CLOSED","message":"request not open"}}

        conn.commit()
        conn.close()

    except Exception:
        logging.exception("RIDE.ACCEPT_REQ failed")
        try:
            if conn:
                conn.rollback()
                conn.close()
        except Exception:
            pass
        return {"type":"ERROR", "id":mid, "payload":{
            "code":"SERVER_ERROR", "message":"Internal Error"
        }}

    # 4) Post-commit side effects: mark driver busy, log, notify passenger once, close others
    with STATE_LOCK:
        BUSY_DRIVERS.add(driver_id)

    logging.info(
        "BOOTSTRAP match: req_%s passenger user_%s <- driver user_%s at %s:%s",
        req_id_int, passenger_id, driver_id, driver_ip, driver_port
    )

    # --- ONLY send RIDE.MATCHED here (post-commit) ---
    passenger = REQUEST_PASSENGERS.get(f"req_{req_id_int}")
    if passenger and passenger.get("sock"):
        driver_info = _driver_info_preview(driver_id)
        _send_json_safe(passenger["sock"], {
            "type": "RIDE.MATCHED",
            "id": _uuid(),
            "payload": {
                "request_id": f"req_{req_id_int}",
                "driver_info": driver_info,
                "driver_ip": driver_ip,
                "driver_port": driver_port
            }
        })

    # Notify remaining drivers that this request is closed
    with STATE_LOCK:
        remaining = ACTIVE_REQUEST_DRIVERS.get(f"req_{req_id_int}", set()).copy()
        if driver_id in remaining:
            remaining.remove(driver_id)
    _notify_request_closed(f"req_{req_id_int}", driver_id, remaining)

    # Cleanup request bookkeeping
    with STATE_LOCK:
        ACTIVE_REQUEST_DRIVERS.pop(f"req_{req_id_int}", None)
        _REQUEST_LAST_TOUCH.pop(f"req_{req_id_int}", None)
        #REQUEST_PASSENGERS.pop(f"req_{req_id_int}", None)

    return {"type":"RIDE.ACCEPT_RES", "id":mid, "payload":{
        "request_id": f"req_{req_id_int}"
    }}

def _mark_driver_sees_request(request_id: str, driver_id: int):
    """Record that this driver is eligible to accept this request."""
    now = time.time()
    with STATE_LOCK:
        ACTIVE_REQUEST_DRIVERS.setdefault(request_id, set()).add(driver_id)
        _REQUEST_LAST_TOUCH[request_id] = now


#FREEING THE DRIVER LATER:
def _free_driver(driver_id: int):
    with STATE_LOCK:
        BUSY_DRIVERS.discard(driver_id)

def _ride_complete(conn_state, payload, mid):
    driver_id, err = require_logged_in(conn_state, mid)
    if err:
        return err
    req_s = (payload or {}).get("request_id")
    req_id_int = _reqid_to_int(req_s)
    if not isinstance(req_id_int, int):
        return {"type":"ERROR", "id":mid, "payload":{
            "code":"BAD_REQUEST",
            "message":"invalid request_id"
        }}
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("UPDATE matches SET status='completed' WHERE request_id=? AND driver_id=?", (req_id_int, driver_id))
        try:
            cur.execute(
            "UPDATE ride_req SET status='completed' WHERE request_id=?",
            (req_id_int,)
            )
        except Exception:
            pass

        conn.commit()
        conn.close()
    except Exception:
        logging.exception("ride_complete")
        return {"type":"ERROR", "id":mid, "payload":{
            "code":"SERVER_ERROR",
            "message":"Internal error"
        }}
    req_key = f"req_{req_id_int}"
    passenger = REQUEST_PASSENGERS.get(req_key)
    if passenger and passenger.get("sock"):
        try:
            _send_json_safe(passenger["sock"], {
                "type": "REQUEST.CLOSED",
                "id": str(uuid.uuid4()),
                "payload":{
                    "request_id":req_key,
                    "winner_user_id":f"user_{driver_id}",
                    "reason":"completed"
                }
            })
        except Exception:
            logging.exception("notify passenger ride complete")
    REQUEST_PASSENGERS.pop(req_key, None)
    _free_driver(driver_id)
    return {"type":"RIDE.COMPLETE_RES", "id":mid, "payload":{}}

def _ride_rate(conn_state, payload, mid):
    """Handle RIDE.RATE_REQ: one side rates the other after a completed ride."""
    rater_id, err = require_logged_in(conn_state, mid)
    if err:
        return err

    p = payload or {}
    req_s = p.get("request_id")
    rating = p.get("rating")

    # validate request_id
    req_id_int = _reqid_to_int(req_s)
    if not isinstance(req_id_int, int):
        return {"type": "ERROR", "id": mid,
                "payload": {"code": "BAD_REQUEST", "message": "invalid request_id"}}

    # validate rating
    if not isinstance(rating, int) or not (1 <= rating <= 5):
        return {"type": "ERROR", "id": mid,
                "payload": {"code": "BAD_REQUEST", "message": "rating must be 1–5"}}

    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        # find match
        cur.execute(
            "SELECT match_id, user_id, driver_id, status FROM matches WHERE request_id=?",
            (req_id_int,)
        )
        row = cur.fetchone()
        if not row:
            conn.close()
            return {"type": "ERROR", "id": mid,
                    "payload": {"code": "NOT_FOUND",
                                "message": "match not found"}}

        match_id, passenger_id, driver_id, status = row

        # determine who is being rated
        if rater_id == driver_id:
            ratee_id = passenger_id
        elif rater_id == passenger_id:
            ratee_id = driver_id
        else:
            conn.close()
            return {"type": "ERROR", "id": mid,
                    "payload": {"code": "FORBIDDEN",
                                "message": "you are not part of this ride"}}

        # insert rating (1 per match per ratee)
        try:
            cur.execute(
                "INSERT INTO ratings(match_id, user1_id, user2_id, stars) VALUES (?,?,?,?)",
                (match_id, rater_id, ratee_id, rating)
            )
        except sqlite3.IntegrityError:
            conn.close()
            return {"type": "ERROR", "id": mid,
                    "payload": {"code": "DUPLICATE",
                                "message": "rating already submitted"}}

        # update user aggregates
        cur.execute("SELECT rating_sum, rating_count FROM users WHERE user_id=?",
                    (ratee_id,))
        s, c = cur.fetchone()
        if s is None: s = 0
        if c is None: c = 0

        new_sum = s + rating
        new_count = c + 1
        new_avg = float(new_sum) / new_count

        cur.execute(
            "UPDATE users SET rating_sum=?, rating_count=?, rating_avg=? WHERE user_id=?",
            (new_sum, new_count, new_avg, ratee_id)
        )

        conn.commit()
        conn.close()

        cur.execute("SELECT name, email, area, is_driver, rating_avg, rating_count FROM users WHERE user_id=?", (rater_id,))
        updated_row = cur.fetchone()
        updated_user = {
            "name": updated_row[0],
            "email": updated_row[1],
            "area": updated_row[2],
            "is_driver": bool(updated_row[3]),
            "rating_avg": updated_row[4],
            "rating_count": updated_row[5],
        }

        return {
            "type": "RIDE.RATE_RES",
            "id": mid,
            "payload": {"request_id": req_s, "updated_user":updated_user}
        }

    except Exception:
        logging.exception("RIDE.RATE_REQ failed")
        try: conn.close()
        except: pass
        return {"type": "ERROR", "id": mid,
                "payload": {"code": "SERVER_ERROR",
                            "message": "failed to record rating"}}


def _cancel_active_matches_for_driver(driver_id: int):
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            "UPDATE matches SET status='cancelled' "
            "WHERE driver_id=? AND status='active'",
            (driver_id,),
        )
        conn.commit()
        conn.close()
    except Exception:
        logging.exception("cancel_active_matches_for_driver failed")

#this is to stop users from making requests if they have a request whose status is open/matched
def _passenger_has_active_request(user_id: int) -> bool:
    """
    Returns True if this passenger already has an active ride request
    (status = 'open' or 'matched'), False otherwise.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
        "SELECT 1 FROM ride_req WHERE user_id=? AND status IN ('open','matched') LIMIT 1",
        (user_id,),
    )


        row = cur.fetchone()
        conn.close()
        return bool(row)
    except Exception:
        logging.exception("_passenger_has_active_request failed")
        # Fail-closed: safest is to treat as 'has active' so we don't break invariants
        return True



# ---------------------------------------------------------
# Dispatcher (takes per-connection state) (NOT UP TO DATE!!)
# Validates 'type' and 'id'
    # mtype switch:
    # - "PING" → PONG
    # - "AUTH.REGISTER_REQ" → register_user(...)
    # - "AUTH.LOGIN_REQ"    → login_user(...) and bind conn_state["user_id"]
    # - "AUTH.LOGOUT_REQ"   → clears conn_state["user_id"]
    # - "PROFILE.SET_REQ"   → requires login
    # - "PROFILE.GET_REQ"   → requires login (or explicit user_id payload) 
    # otherwise → ERROR: UNKNOWN_TYPE
# ---------------------------------------------------------

def handle_message(msg: dict, conn_state: dict):
    if "type" not in msg or "id" not in msg:
        return {"type": "ERROR", "id": msg.get("id"),
                "payload": {"code": "BAD_REQUEST", "message": "Missing required field(s): type, id"}}
    if not is_valid_uuid4(msg["id"]):
        return {"type": "ERROR", "id": msg.get("id"),
                "payload": {"code": "BAD_REQUEST", "message": "Field 'id' must be a valid UUIDv4 string"}}

    _gc_requests()
    
    mtype   = msg["type"]
    mid     = msg["id"]
    payload = msg.get("payload") or {}

    # CONTROL
    if mtype == "PING":
        return {"type": "PONG", "id": mid, "payload": {}}

    # AUTH
    if mtype == "AUTH.REGISTER_REQ":
        ok, res = register_user(payload)
        return {"type": "AUTH.REGISTER_RES" if ok else "ERROR", "id": mid, "payload": res}

    if mtype == "AUTH.LOGIN_REQ":
        ok, res = login_user(payload)
        if ok:
            uid = res["user_id_int"]
            conn_state["user_id"] = uid  # bind this socket to the user
            user_preview = res["user"]

            if user_preview.get("is_driver"):
                with STATE_LOCK:
                
                    ONLINE_DRIVERS[uid] = conn_state.get("sock")

                    ip = conn_state["peer"][0] if conn_state.get("peer") else None


                    
            else:
                with STATE_LOCK:
                    ONLINE_DRIVERS.pop(uid, None)
                    DRIVER_PEERS.pop(uid, None)

            return {"type": "AUTH.LOGIN_RES", "id": mid, "payload": {"user": user_preview}}
        else:
            return {"type": "ERROR", "id": mid, "payload": res}


    if mtype == "AUTH.LOGOUT_REQ":
        uid = conn_state.get("user_id")
        if uid is not None:
            _cancel_active_matches_for_driver(uid)
            _free_driver(uid)

        with STATE_LOCK:
            if uid in ONLINE_DRIVERS:
                ONLINE_DRIVERS.pop(uid, None)
            if uid in DRIVER_PEERS:
                DRIVER_PEERS.pop(uid, None)

        conn_state["user_id"] = None
        return {"type":"AUTH.LOGOUT_RES", "id":mid, "payload":{
            "message":"Logout Successful"
        }}

    # PROFILE (require connection-bound login)
    if mtype == "PROFILE.SET_REQ":
        resp = profile_set(conn_state.get("user_id"), payload, mid)
        if resp.get("type") == "PROFILE.SET_RES" and isinstance(payload, dict) and "is_driver" in payload:
            uid = conn_state.get("user_id")
            if uid is not None:
                if payload.get("is_driver"):
                    with STATE_LOCK:
                        ONLINE_DRIVERS[uid] = conn_state.get("sock")
                        ip = conn_state["peer"][0] if conn_state.get("peer") else None
                        
                else:
                    with STATE_LOCK:
                        ONLINE_DRIVERS.pop(uid, None)
                        DRIVER_PEERS.pop(uid, None)
        return resp

    if mtype == "PROFILE.GET_REQ":
        return profile_get(conn_state.get("user_id"), payload, mid)

    
    #scheduke(require login, set/remove require driver)
    if mtype == "SCHEDULE.SET_REQ":
        return schedule_set(conn_state, payload, mid)
    if mtype == "SCHEDULE.LIST_REQ":
        return schedule_get(conn_state, payload, mid)
    if mtype == "SCHEDULE.REMOVE_REQ":
        return schedule_remove(conn_state, payload, mid)
    
    #ride rrequests:
    if mtype == "RIDE.REQUEST_REQ":
        uid, err = require_logged_in(conn_state, mid)
        if err:
            return err

        p = payload or {}
        area = p.get("area")           # still required for display
        direction = p.get("direction")
        time_iso = p.get("time_iso")
        lat = p.get("lat")
        lon = p.get("lon")

        # Optional: minimum driver rating (1–5) requested by passenger
        min_driver_rating = p.get("min_driver_rating")
        if isinstance(min_driver_rating, (int, float)):
            min_driver_rating = float(min_driver_rating)
            # clamp to sensible range or disable if nonsense
            if not (0.0 <= min_driver_rating <= 5.0):
                min_driver_rating = None
        else:
            min_driver_rating = None


        if not isinstance(area, str) or not area.strip():
            return {
                "type": "ERROR",
                "id": mid,
                "payload": {"code": "BAD_REQUEST", "message": "area required"},
            }
        if direction not in ("to_AUB", "from_AUB"):
            return {
                "type": "ERROR",
                "id": mid,
                "payload": {
                    "code": "BAD_REQUEST",
                    "message": "direction must be 'to_AUB' or 'from_AUB'",
                },
            }
        if not isinstance(time_iso, str) or not time_iso.strip():
            return {
                "type": "ERROR",
                "id": mid,
                "payload": {"code": "BAD_REQUEST", "message": "time_iso required"},
            }

        try:
            weekday_sun0, req_minutes = _minutes_from_iso(time_iso)
        except Exception:
            return {
                "type": "ERROR",
                "id": mid,
                "payload": {
                    "code": "BAD_REQUEST",
                    "message": "time_iso must be valid ISO",
                },
            }

        # New: require numeric lat/lon for the pin
        try:
            lat = float(lat)
            lon = float(lon)
        except (TypeError, ValueError):
            return {
                "type": "ERROR",
                "id": mid,
                "payload": {"code": "BAD_REQUEST", "message": "lat and lon must be numeric"},
            }

        # Enforce at most one active request per passenger
        if _passenger_has_active_request(uid):
            return {
                "type": "ERROR",
                "id": mid,
                "payload": {
                    "code": "PASSENGER_BUSY",
                    "message": "You already have an active ride request. Please cancel or complete it before creating a new one.",
                },
            }

        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            # 1) create request row with lat/lon
            cur.execute(
                """
                INSERT INTO ride_req (user_id, area, direction, departure_time, lat, lon, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'open', CURRENT_TIMESTAMP)
                """,
                (uid, area, direction, time_iso, lat, lon),
            )
            req_id_int = cur.lastrowid
            request_id = f"req_{req_id_int}"

            # 2) find candidate driver schedules:
            #    same weekday, same direction, compatible time window.
            #    area is *ignored* for matching now.
            cur.execute(
                """
                SELECT s.user_id,
                       s.depart_time,
                       s.lat,
                       s.lon,
                       u.rating_avg,
                       u.rating_count
                FROM schedules s
                JOIN users u ON u.user_id = s.user_id
                WHERE s.weekday=? AND s.direction=? AND u.is_driver=1
                """,
                (weekday_sun0, direction),
            )
            rows = cur.fetchall()

            conn.commit()
            conn.close()

            CUTOFF_MIN = 30
            RADIUS_KM = 1.0

            candidate_ids = []
            for driver_id, depart_hhmm, dlat, dlon, rating_avg, rating_count in rows:
                #rating 
                if min_driver_rating is not None:
                    driver_rating = float(rating_avg) if rating_avg is not None else 0.0
                    if driver_rating < min_driver_rating:
                        continue

                # Require driver to have a pin as well
                try:
                    dlat = float(dlat)
                    dlon = float(dlon)
                except (TypeError, ValueError):
                    continue

                try:
                    sched_minutes = _minutes_from_hhmm(depart_hhmm)
                except Exception:
                    continue

                # Time window check
                if abs(sched_minutes - req_minutes) > CUTOFF_MIN:
                    continue

                # Distance check using haversine
                dist_km = haversine_km(lat, lon, dlat, dlon)
                if dist_km > RADIUS_KM:
                    continue

                if int(driver_id) == uid:
                    continue  # don't match with yourself

                candidate_ids.append(int(driver_id))

            passenger_preview = {
                "user_id": f"user_{uid}",
                "area": area,
                "direction": direction,
                "time_iso": time_iso,
                "request_id": request_id,
                "lat": lat,
                "lon": lon,
            }

            # remember passenger socket so we can notify upon match
            with STATE_LOCK:
                REQUEST_PASSENGERS[request_id] = {
                    "user_id": uid,
                    "sock": conn_state.get("sock"),
                }

            sent = _broadcast_driver_candidates(request_id, passenger_preview, candidate_ids)

            return {
                "type": "RIDE.REQUEST_RES",
                "id": mid,
                "payload": {
                    "request_id": request_id,
                    "candidates_found": len(candidate_ids),
                    "broadcasted_to_online": sent,
                },
            }

        except Exception:
            logging.exception("RIDE.REQUEST_REQ failed")
            return {
                "type": "ERROR",
                "id": mid,
                "payload": {"code": "SERVER_ERROR", "message": "Failed to create request"},
            }

    if mtype == "RIDE.LIST_REQ":
        driver_id, err = require_logged_in(conn_state, mid)
        if err:
            return err

        _ok, derr = require_driver(conn_state, mid)
        if derr:
            return derr
        
        #rating
        p = payload or {}
        min_passenger_rating = p.get("min_passenger_rating")
        if isinstance(min_passenger_rating, (int, float)):
            min_passenger_rating = float(min_passenger_rating)
            if not (0.0 <= min_passenger_rating <= 5.0):
                min_passenger_rating = None
        else:
            min_passenger_rating = None


        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()

            # Driver's schedules, including lat/lon
            cur.execute(
                """
                SELECT weekday, depart_time, direction, lat, lon
                FROM schedules
                WHERE user_id=?
                """,
                (driver_id,),
            )
            driver_scheds = cur.fetchall()

            if not driver_scheds:
                conn.close()
                return {
                    "type": "RIDE.LIST_RES",
                    "id": mid,
                    "payload": {"items": []},
                }

            # All open ride requests WITH lat/lon + rating
            cur.execute(
                """
                SELECT r.request_id,
                       r.user_id,
                       r.area,
                       r.direction,
                       r.departure_time,
                       r.lat,
                       r.lon,
                       u.rating_avg,
                       u.rating_count
                FROM ride_req AS r
                JOIN users AS u ON u.user_id = r.user_id
                WHERE r.status='open'
                """
            )
            req_rows = cur.fetchall()

            conn.close()

            CUTOFF_MIN = 30
            RADIUS_KM = 1.0

            items = []

            for req_id_int, passenger_id, area, direction, dep_time, plat, plon, rating_avg, rating_count in req_rows:
                # --- A) Check passenger's min_driver_rating against THIS driver's rating ---
                # Fetch driver's rating (average)
                cur2 = sqlite3.connect(DB_PATH).cursor()
                cur2.execute("SELECT rating_avg FROM users WHERE user_id=?", (driver_id,))
                row = cur2.fetchone()
                driver_rating_avg = float(row[0]) if row and row[0] is not None else 0.0

                # Fetch passenger's required minimum rating for drivers
                cur3 = sqlite3.connect(DB_PATH).cursor()
                cur3.execute("SELECT min_driver_rating FROM ride_req WHERE request_id=?", (req_id_int,))
                min_driver_rating_row = cur3.fetchone()
                min_driver_rating_for_this_request = min_driver_rating_row[0] if min_driver_rating_row else None

                # If passenger required a minimum & driver doesn’t meet it → SKIP
                if min_driver_rating_for_this_request is not None:
                    if driver_rating_avg < float(min_driver_rating_for_this_request):
                        continue
                
                # Skip requests without coords
                try:
                    plat = float(plat)
                    plon = float(plon)
                except (TypeError, ValueError):
                    continue

                try:
                    weekday_sun0, req_minutes = _minutes_from_iso(dep_time)
                except Exception:
                    continue

                compatible = False
                for wd, depart_hhmm, s_dir, dlat, dlon in driver_scheds:
                    if s_dir != direction:
                        continue
                    if wd != weekday_sun0:
                        continue

                    try:
                        dlat = float(dlat)
                        dlon = float(dlon)
                    except (TypeError, ValueError):
                        continue

                    try:
                        sched_minutes = _minutes_from_hhmm(depart_hhmm)
                    except Exception:
                        continue

                    if abs(sched_minutes - req_minutes) > CUTOFF_MIN:
                        continue

                    dist_km = haversine_km(plat, plon, dlat, dlon)
                    if dist_km <= RADIUS_KM:
                        compatible = True
                        break

                if not compatible:
                    continue

                if passenger_id == driver_id:
                    continue

                request_key = f"req_{req_id_int}"

                items.append(
                    {
                        "request_id": request_key,
                        "user_id": f"user_{passenger_id}",
                        "area": area,  # for display only
                        "direction": direction,
                        "time_iso": dep_time,
                    }
                )
                _mark_driver_sees_request(request_key, driver_id)

            return {
                "type": "RIDE.LIST_RES",
                "id": mid,
                "payload": {"items": items},
            }

        except Exception:
            logging.exception("RIDE.LIST_REQ failed")
            return {
                "type": "ERROR",
                "id": mid,
                "payload": {
                    "code": "SERVER_ERROR",
                    "message": "Failed to list ride requests",
                },
            }

        
    if mtype == "RIDE.ACCEPT_REQ":
        return _ride_accept(conn_state, payload, mid)
    
    if mtype == "DRIVER.RESPONSE_REQ":
        uid, err = require_logged_in(conn_state, mid)
        if err: return err
        _ok, derr = require_driver(conn_state, mid)
        if derr: return derr

        decision = (payload or {}).get("decision")
        req_id = (payload or {}).get("request_id")

        if decision not in ("accept", "reject"):
            return {"type":"ERROR","id":mid,"payload":{"code":"BAD_REQUEST","message":"decision must be 'accept' or 'reject'"}}

        if decision == "reject":
            # optional: record a decline; then respond
            return {"type":"DRIVER.RESPONSE_RES","id":mid,"payload":{"status":"declined"}}

        # accept path: reuse your existing logic
        r = _ride_accept(conn_state, {"request_id": req_id}, mid)
        if r.get("type") == "RIDE.ACCEPT_RES":
            return {"type":"DRIVER.RESPONSE_RES","id":mid,"payload":{"status":"accepted","request_id": r["payload"]["request_id"]}}
        else:
            # translate server error into RESPONSE_RES or forward the ERROR directly
            if r.get("type") == "ERROR":
                return r
            return {"type":"ERROR","id":mid,"payload":{"code":"SERVER_ERROR","message":"accept failed"}}
    
    if mtype == "RIDE.CANCEL_REQ":
        uid, err = require_logged_in(conn_state, mid)
        if err:
            return err

        p = payload or {}
        req_id = p.get("request_id")
        if not isinstance(req_id, str) or not req_id.startswith("req_"):
            return {
                "type": "ERROR",
                "id": mid,
                "payload": {
                    "code": "BAD_REQUEST",
                    "message": "request_id must be like 'req_<int>'",
                },
            }
        try:
            req_id_int = int(req_id.split("_", 1)[1])
        except Exception:
            return {
                "type": "ERROR",
                "id": mid,
                "payload": {
                    "code": "BAD_REQUEST",
                    "message": "invalid request_id",
                },
            }

        # Load request
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute(
                "SELECT user_id, status FROM ride_req WHERE request_id=?",
                (req_id_int,),
            )
            row = cur.fetchone()
            if not row:
                conn.close()
                return {
                    "type": "ERROR",
                    "id": mid,
                    "payload": {
                        "code": "NOT_FOUND",
                        "message": "Request not found",
                    },
                }
            passenger_id, status = row

            # Only creator can cancel
            if passenger_id != uid:
                conn.close()
                return {
                    "type": "ERROR",
                    "id": mid,
                    "payload": {
                        "code": "FORBIDDEN",
                        "message": "You can only cancel your own requests",
                    },
                }

            # For simplicity, allow cancel only while still open
            if status != "open":
                conn.close()
                return {
                    "type": "ERROR",
                    "id": mid,
                    "payload": {
                        "code": "INVALID_STATE",
                        "message": "Only open requests can be cancelled",
                    },
                }

            # Mark as cancelled
            cur.execute(
                "UPDATE ride_req SET status='cancelled' WHERE request_id=?",
                (req_id_int,),
            )
            conn.commit()
            conn.close()
        except Exception:
            logging.exception("RIDE.CANCEL_REQ failed")
            return {
                "type": "ERROR",
                "id": mid,
                "payload": {
                    "code": "SERVER_ERROR",
                    "message": "Failed to cancel request",
                },
            }

        # Clean up in-memory tracking
        req_key = f"req_{req_id_int}"
        with STATE_LOCK:
            ACTIVE_REQUEST_DRIVERS.pop(req_key, None)
            _REQUEST_LAST_TOUCH.pop(req_key, None)
            REQUEST_PASSENGERS.pop(req_key, None)

        
        return {
            "type": "RIDE.CANCEL_RES",
            "id": mid,
            "payload": {"request_id": req_key},
        }
    
    if mtype == "PEER.ANNOUNCE_REQ":
        uid, err = require_logged_in(conn_state, mid)
        if err:
            return err
        p = payload or {}
        peer_port = p.get("peer_port")
        ip, port = _normalize_peer_endpoint(conn_state, peer_port)
        if ip is None or port is None:
            return {"type":"ERROR", "id":mid, "payload":{
                "code":"BAD_REQUEST",
                "message":"Provide peer port after logging in as a driver"
            }}
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT is_driver FROM users WHERE user_id=?", (uid,))
            row = cur.fetchone(); conn.close()
            if not row or int(row[0]) != 1:
                return {"type":"ERROR", "id":mid, "payload":{
                "code":"FORBIDDEN",
                "message":"driver mode must be on"
            }}
        except Exception:
            logging.exception("PEER>ANNOUNCE check failed")
        with STATE_LOCK:
            DRIVER_PEERS[uid] = (ip, port)
            ONLINE_DRIVERS[uid] = conn_state.get("sock")
        logging.info("PEER announced: user_%s -> %s:%s", uid, ip, port)
        return {"type":"PEER.ANNOUNCE_RES","id":mid,"payload":{"ip":ip,"port":port}}
    
    # PEER.OPEN_REQ — driver declares its P2P listening port (TCP)
    if mtype == "PEER.OPEN_REQ":
        uid, err = require_logged_in(conn_state, mid)
        if err:
            return err

        # Correct driver check (require_driver returns (ok, err))
        _ok, derr = require_driver(conn_state, mid)
        if derr:
            return derr

        p = payload or {}
        p2p_port = p.get("p2p_port")
        ext_ip    = p.get("external_ip")   # optional, if driver discovered it via UPnP/NAT-PMP
        ext_port  = p.get("external_port") # optional, if mapping returns a different external port

        # Fallback IP = server-observed remote IP of this control connection
        seen_ip = conn_state["peer"][0] if conn_state.get("peer") else None

        # Choose best info we have
        ip   = ext_ip or seen_ip
        port = ext_port or (p2p_port if isinstance(p2p_port, int) and 1 <= p2p_port <= 65535 else None)

        if not ip or not port:
            return {
                "type": "ERROR",
                "id": mid,
                "payload": {"code": "BAD_REQUEST", "message": "Provide p2p_port (and external_ip/port if known)"}
            }

        # Save endpoint for _ride_accept and mark driver online
        with STATE_LOCK:
            DRIVER_PEERS[uid]   = (ip, port)
            ONLINE_DRIVERS[uid] = conn_state.get("sock")

        logging.info("PEER.OPEN: user_%s reachable at %s:%s", uid, ip, port)

        return {"type": "PEER.OPEN_RES", "id": mid, "payload": {"ip": ip, "port": port}}
    
    if mtype == "RIDE.COMPLETE_REQ":
        return _ride_complete(conn_state, payload, mid)

    if mtype == "RIDE.RATE_REQ":
        return _ride_rate(conn_state, payload, mid)
    
    # Unknown
    return {"type": "ERROR", "id": mid, "payload": {"code": "UNKNOWN_TYPE", "message": f"Unsupported type: {mtype}"}}

# ---------------------------------------------------------
# Per-client thread & server
# ---------------------------------------------------------
def client_thread(conn: socket.socket, addr):
    peer = f"{addr[0]}:{addr[1]}"
    logging.info("Client connected: %s", peer)

    # Per-connection state (no tokens; socket-bound)
    conn_state = {"user_id": None, "sock": conn, "peer": addr}

    try:
        for line in recv_lines(conn):
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                send_json(conn, {"type": "ERROR", "id": None, "payload": {"code": "BAD_JSON", "message": "Invalid JSON line"}})
                continue
            try:
                resp = handle_message(msg, conn_state)
            except Exception:
                logging.error("Handler error:\n%s", traceback.format_exc())
                resp = {"type": "ERROR", "id": msg.get("id"), "payload": {"code": "SERVER_ERROR", "message": "Internal error"}}
            send_json(conn, resp)
    except (ConnectionResetError, BrokenPipeError):
        logging.info("Client reset: %s", peer)
    finally:
        try:
            uid = conn_state.get("user_id")
            with STATE_LOCK:
                if uid in ONLINE_DRIVERS and ONLINE_DRIVERS.get(uid) is conn:
                    ONLINE_DRIVERS.pop(uid, None)
                DRIVER_PEERS.pop(uid, None)
                conn.close()
        except Exception:
            pass
        logging.info("Client disconnected: %s", peer)
        if uid is not None:
            _cancel_active_matches_for_driver(uid)
            _free_driver(uid)
            

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
            logging.info("Shutting down server")
        finally:
            for t in threads:
                t.join(timeout=0.1)


def main():
    parser = argparse.ArgumentParser(description="AUBus JSON-L server (no tokens; connection-bound auth)")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=6000)
    parser.add_argument("--log", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log.upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(message)s")

    serve(args.host, args.port)

if __name__ == "__main__":
    main()
