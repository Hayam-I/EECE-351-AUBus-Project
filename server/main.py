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
  
N.B TO SELF: password is plaintext, consider TLS, later not rn
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
ONLINE_DRIVERS: dict[int, socket.socket] = {}
ACTIVE_REQUEST_DRIVERS: dict[str, set[int]] = defaultdict(set)
_REQUEST_LAST_TOUCH: dict[str, float] = {}
REQUEST_TTL_SECONDS = 120  # tune as needed

# ---------------------------
# UUIDv4 validation
# ---------------------------
def is_valid_uuid4(value: str) -> bool:
    if not isinstance(value, str):
        return False
    try:
        u = uuid.UUID(value, version=4)
    except (ValueError, TypeError):
        return False
    return str(u) in (value, value.lower(), value.upper())

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

# ---------------------------------------------------------
# Validation helpers (registration/login/schedule)
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

def _uuid() -> str:
    return str(uuid.uuid4())

def _send_json_safe(sock: socket.socket, obj: dict):
    try:
        send_json(sock, obj)
    except Exception:
        logging.exception("send failed")

def _parse_user_id_any(u) -> int | None:
    """
    Accept either internal int (7) or external 'user_7' and return 7.
    """
    if isinstance(u, int):
        return u
    if isinstance(u, str) and u.startswith("user_"):
        try:
            return int(u.split("_", 1)[1])
        except ValueError:
            return None
    return None

def _minutes_from_hhmm(s:str) -> int:
    hh,mm = s.split(":")
    return int(hh) * 60 + int(mm)

def _minutes_from_iso(iso_s: str) -> tuple[int, int]:
    dt = datetime.fromisoformat(iso_s.replace(" ","T"))
    py_wd = dt.weekday()
    sun0 = (py_wd + 1)%7
    minutes = dt.hour * 60 + dt.minute
    return sun0, minutes

def _broadcast_driver_candidates(request_id: str, passenger_preview: dict, candidate_user_ids: list[int]):
    ACTIVE_REQUEST_DRIVERS.setdefault(request_id, set())
    now = time.time()
    sent = 0
    for uid in candidate_user_ids:
        sock = ONLINE_DRIVERS.get(uid)
        if not sock:
            continue
        _send_json_safe(sock, {
            "type": "DRIVER.BROADCAST",
            "id": _uuid(),
            "payload": {
                "request_id": request_id,
                "passenger_preview": passenger_preview
            }
        })
        ACTIVE_REQUEST_DRIVERS[request_id].add(uid)
        sent += 1
    _REQUEST_LAST_TOUCH[request_id] = now
    return sent

def _notify_request_closed(request_id: str, winner_uid: int, remaining: set[int]):
    for uid in list(remaining):
        sock = ONLINE_DRIVERS.get(uid)
        if not sock:
            continue
        _send_json_safe(sock, {
            "type": "REQUEST.CLOSED",
            "id": _uuid(),
            "payload": {
                "request_id": request_id,
                "winner_user_id": f"user_{winner_uid}"
            }
        })

def _on_exhausted_candidates(request_id: str):
    # Hook: you can expand search, notify passenger, etc.
    logging.info("request %s: no remaining driver candidates", request_id)

def _gc_requests():
    now = time.time()
    for req_id, ts in list(_REQUEST_LAST_TOUCH.items()):
        if now - ts > REQUEST_TTL_SECONDS:
            logging.info("GC: expiring request %s", req_id)
            ACTIVE_REQUEST_DRIVERS.pop(req_id, None)
            _REQUEST_LAST_TOUCH.pop(req_id, None)

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
            "SELECT user_id,name,username,password,email,is_driver,area,rating_sum,rating_avg,rating_count "
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
                "INSERT INTO profiles (user_id, is_driver, area, vehicle_make, vehicle_model, vehicle_color, vehicle_plate) "
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
                "UPDATE profiles SET is_driver=?, area=?, vehicle_make=?, vehicle_model=?, vehicle_color=?, vehicle_plate=? "
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
            "rating": float(row[8]) if row[8] is not None else 0.0,
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
    if err: return err
    _ok, derr = require_driver(conn_state, mid)
    if derr: return derr

    ok, msg = validate_schedule_payload(payload or {})
    if not ok:
        return {"type": "ERROR", "id": mid, "payload": {"code": "BAD_REQUEST", "message": msg}}

    p = payload
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        cur.execute("BEGIN IMMEDIATE") #to lock write into db when checking for duplicates/adding new
        cur.execute("""
        SELECT 1 FROM schedules WHERE user_id=? AND weekday=? AND depart_time=? AND direction=? AND area=?
                    LIMIT 1 
                    """, (uid, p["weekday"], p["depart_time"], p["direction"], p["area"]))
        if cur.fetchone():
            conn.rollback()
            conn.close()
            return{
                "type":"ERROR",
                "id":mid,
                "payload": {
                    "code": "SCHEDULE_DUPLICATE",
                    "message":"This exact schedule already exists"
                }
            }
        cur.execute(
            "INSERT INTO schedules (user_id, weekday, depart_time, direction, area) VALUES (?, ?, ?, ?, ?)",
            (uid, p["weekday"], p["depart_time"], p["direction"], p["area"])
        )
        schedule_id = cur.lastrowid
        conn.commit()
        conn.close()
        return {"type": "SCHEDULE.SET_RES", "id": mid, "payload": {"schedule_id": schedule_id}}
    except Exception:
        logging.exception("schedule_set failed")
        return {"type": "ERROR", "id": mid, "payload": {"code": "SERVER_ERROR", "message": "Failed to set schedule"}}


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

def ride_request_new(conn_state, payload, mid):
    uid, err = require_logged_in(conn_state, mid)
    if err:
        return err
    
    p = payload or {}
    area = p.get("area")
    direction = p.get("direction")
    time_iso = p.get("time_iso")
    
    if not isinstance(area,str) or not area.strip():
        return {"type":"ERROR", "id":mid, "payload":{
            "code": "BAD_REQUEST", "message":"area(str) required"
        }}
    if direction not in("to_AUB", "from_AUB"):
        return {"type":"ERROR", "id":mid, "payload":{
            "code":"BAD_REQUEST",
            "message": "direction must be to and from AUB"
        }}
    if not isinstance(time_iso, str) or not time_iso.strip():
        return {"type":"ERROR", "id":mid, "payload":{
            "code":"BAD_REQUEST",
            "message":"time_iso required"
        }}
    try:
        weekday_sun0, req_minutes = _minutes_from_iso(time_iso)
    except Exception:
        return {"type":"ERROR", "id": mid, "payload":{
            "code":"BAD_REQUEST",
            "message":"time iso must be valid iso time"
        }}
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
         # 1) create ride request row
        cur.execute("""
            INSERT INTO ride_req (user_id, area, direction, departure_time, status, created_at)
            VALUES (?, ?, ?, ?, 'open', CURRENT_TIMESTAMP)
        """, (uid, area, direction, time_iso))
        request_id_int = cur.lastrowid
        request_id_str = f"req_{request_id_int}"

        # 2) fetch candidate driver schedules (same weekday/area/direction; drivers only)
        cur.execute("""
            SELECT s.user_id, s.depart_time
            FROM schedules s
            JOIN users u ON u.user_id = s.user_id
            WHERE s.weekday=? AND s.area=? AND s.direction=? AND u.is_driver=1
        """, (weekday_sun0, area, direction))
        rows = cur.fetchall()
        conn.commit()
        conn.close()

        # 3) filter by ±30 minutes around requested time
        CUTOFF = 30
        candidate_ids = []
        for user_id_, depart_hhmm in rows:
            try:
                if abs(_minutes_from_hhmm(depart_hhmm) - req_minutes) <= CUTOFF:
                    candidate_ids.append(int(user_id_))
            except Exception:
                pass  # skip malformed rows safely

        passenger_preview = {
            "user_id": f"user_{uid}",
            "area": area,
            "direction": direction,
            "time_iso": time_iso,
            "request_id": request_id_str,
        }

        # 4) broadcast only to candidates who are currently online
        sent = _broadcast_driver_candidates(request_id_str, passenger_preview, candidate_ids)

        return {
            "type": "RIDE.REQUEST_RES",
            "id": mid,
            "payload": {
                "request_id": request_id_str,
                "candidates_found": len(candidate_ids),
                "broadcasted_to_online": sent
            }
        }
    except Exception:
        logging.exception("ride_request_new failed")
        return {"type":"ERROR","id":mid,"payload":{"code":"SERVER_ERROR","message":"Failed to create request"}}

    
# ---------------------------------------------------------
# Dispatcher (takes per-connection state)
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
            conn_state["user_id"] = res["user_id_int"]  # bind this socket to the user
            # Don't leak the internal int in payload; return only user preview
            if res["user"].get("is_driver"):
                ONLINE_DRIVERS[res["user_id_int"]] = conn_state.get("sock")

            return {"type": "AUTH.LOGIN_RES", "id": mid, "payload": {"user": res["user"]}}
        else:
            return {"type": "ERROR", "id": mid, "payload": res}

    if mtype == "AUTH.LOGOUT_REQ":
        uid = conn_state.get("user_id")
        if uid in ONLINE_DRIVERS:
            ONLINE_DRIVERS.pop(uid,None)
        conn_state["user_id"] = None
        return {"type": "AUTH.LOGOUT_RES", "id": mid, "payload": {"message": "Logout Successful"}}

    # PROFILE (require connection-bound login)
    if mtype == "PROFILE.SET_REQ":
        resp = profile_set(conn_state.get("user_id"), payload, mid)
        # If driver flag is being changed, reflect presence map
        if resp.get("type") == "PROFILE.SET_RES" and isinstance(payload, dict) and "is_driver" in payload:
            uid = conn_state.get("user_id")
            if payload.get("is_driver"):
                ONLINE_DRIVERS[uid] = conn_state.get("sock")
            else:
                ONLINE_DRIVERS.pop(uid, None)
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


    # RIDE: passenger posts a new request; server broadcasts to candidate drivers
    if mtype == "RIDE.NEW_REQ":
        # payload: { request_id: str, passenger_preview: {...}, candidate_user_ids: [int or 'user_#'] }
        req_id = payload.get("request_id")
        if not isinstance(req_id, str) or not req_id:
            return {"type": "ERROR", "id": mid, "payload": {"code": "BAD_REQUEST", "message": "request_id (str) required"}}

        passenger_preview = payload.get("passenger_preview") or {}
        cands_in = payload.get("candidate_user_ids") or []
        cand_ids: list[int] = []
        for x in cands_in:
            u = _parse_user_id_any(x)
            if u is not None:
                cand_ids.append(u)

        sent = _broadcast_driver_candidates(req_id, passenger_preview, cand_ids)
        return {"type": "RIDE.NEW_RES", "id": mid, "payload": {"broadcasted": sent}}
    
    if mtype == "RIDE.REQUEST_REQ":
        return ride_request_new(conn_state, payload, mid)
    
    # DRIVER: driver replies accept/reject for a request they received
    if mtype == "DRIVER.RESPONSE_REQ":
        # payload: { request_id: str, decision: 'accept'|'reject' }
        req_id = payload.get("request_id")
        decision = payload.get("decision")
        if not isinstance(req_id, str) or decision not in ("accept", "reject"):
            return {"type": "ERROR", "id": mid, "payload": {"code": "BAD_REQUEST", "message": "request_id + decision required"}}

        uid = conn_state.get("user_id")
        if not uid:
            return {"type": "ERROR", "id": mid, "payload": {"code": "FORBIDDEN", "message": "Login required"}}

        active = ACTIVE_REQUEST_DRIVERS.get(req_id)
        if not active:
            return {"type": "DRIVER.RESPONSE_RES", "id": mid, "payload": {"status": "ignored", "reason": "unknown_request"}}

        # only consider if this driver was actually a candidate
        if uid not in active:
            return {"type": "DRIVER.RESPONSE_RES", "id": mid, "payload": {"status": "ignored", "reason": "not_a_candidate"}}

        active.discard(uid)
        _REQUEST_LAST_TOUCH[req_id] = time.time()

        if decision == "accept":
            # inform remaining drivers that the request is closed
            _notify_request_closed(req_id, winner_uid=uid, remaining=active.copy())
            ACTIVE_REQUEST_DRIVERS.pop(req_id, None)
            _REQUEST_LAST_TOUCH.pop(req_id, None)
            return {"type": "DRIVER.RESPONSE_RES", "id": mid, "payload": {"status": "accepted"}}

        # decision == "reject"
        if not active:
            _on_exhausted_candidates(req_id)
            ACTIVE_REQUEST_DRIVERS.pop(req_id, None)
            _REQUEST_LAST_TOUCH.pop(req_id, None)
        return {"type": "DRIVER.RESPONSE_RES", "id": mid, "payload": {"status": "recorded", "remaining": len(active) if active else 0}}
    
    


    # Unknown
    return {"type": "ERROR", "id": mid, "payload": {"code": "UNKNOWN_TYPE", "message": f"Unsupported type: {mtype}"}}

# ---------------------------------------------------------
# Per-client thread & server
# ---------------------------------------------------------
def client_thread(conn: socket.socket, addr):
    peer = f"{addr[0]}:{addr[1]}"
    logging.info("Client connected: %s", peer)

    # Per-connection state (no tokens; socket-bound)
    conn_state = {"user_id": None, "sock": conn}

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
            if uid in ONLINE_DRIVERS and ONLINE_DRIVERS.get(uid) is conn:
                ONLINE_DRIVERS.pop(uid, None)
            conn.close()
        except Exception:
            pass
        logging.info("Client disconnected: %s", peer)

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
