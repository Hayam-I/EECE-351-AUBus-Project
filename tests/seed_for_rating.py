import sqlite3
import random
import time

DB_PATH = "database.db"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

print("\n=== Resetting rating aggregates & inserting test users ===")

# ------------------------------------------------------------
# 1. TEST USERS WITH INTENTIONAL RATING SPREAD
# ------------------------------------------------------------

passengers = [
    ("Low Rated Passenger",    "p_low",    "pass123", "p_low@example.com",    0, "Hamra"),
    ("Mid Rated Passenger",    "p_mid",    "pass123", "p_mid@example.com",    0, "Hamra"),
    ("High Rated Passenger",   "p_high",   "pass123", "p_high@example.com",   0, "Hamra"),
    ("Unrated Passenger",      "p_none",   "pass123", "p_none@example.com",   0, "Hamra"),
]

drivers = [
    ("Low Rated Driver",       "d_low",    "driver123", "d_low@example.com",    1, "Hamra"),
    ("Mid Rated Driver",       "d_mid",    "driver123", "d_mid@example.com",    1, "Hamra"),
    ("High Rated Driver",      "d_high",   "driver123", "d_high@example.com",   1, "Hamra"),
    ("Unrated Driver",         "d_none",   "driver123", "d_none@example.com",   1, "Hamra"),
]

cur.executemany(
    """
    INSERT OR IGNORE INTO users (name, username, password, email, is_driver, area)
    VALUES (?, ?, ?, ?, ?, ?)
    """,
    passengers + drivers,
)

# ------------------------------------------------------------
# 2. FETCH USER IDS BACK
# ------------------------------------------------------------

def fetch_user_ids(usernames):
    cur.execute(
        f"SELECT user_id, username FROM users WHERE username IN ({','.join('?' for _ in usernames)})",
        usernames
    )
    return {username: user_id for user_id, username in cur.fetchall()}

pass_ids  = fetch_user_ids([x[1] for x in passengers])
driver_ids = fetch_user_ids([x[1] for x in drivers])

# ------------------------------------------------------------
# 3. FAKE RATINGS
# ------------------------------------------------------------
# Structure: username → list of star ratings given by others
preset_ratings = {
    "p_low":  [1, 1, 2],
    "p_mid":  [3, 4],
    "p_high": [5, 5, 4, 5],
    "p_none": [],

    "d_low":  [1, 2],
    "d_mid":  [3, 3, 4],
    "d_high": [5, 5, 4, 5, 5],
    "d_none": [],
}

print("\n=== Seeding ratings and recalculating aggregates ===")

# wipe ratings for clean test
cur.execute("DELETE FROM ratings")

rating_id_counter = 1

for username, stars_list in preset_ratings.items():
    uid = pass_ids.get(username) or driver_ids.get(username)

    # wipe aggregates
    cur.execute(
        "UPDATE users SET rating_sum=0, rating_count=0, rating_avg=0 WHERE user_id=?",
        (uid,)
    )

    for stars in stars_list:
        # Insert a fake match row so ratings table FK does not break
        cur.execute(
            """
            INSERT INTO matches (request_id, user_id, driver_id, area, direction, departure_time,
                                 status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                random.randint(1, 999999),     # fake request_id
                uid,                            # passenger (placeholder)
                uid,                            # driver (placeholder)
                "Hamra",
                "to_AUB",
                "09:00",
                "completed",
                time.time()
            )
        )
        match_id = cur.lastrowid

        # Insert rating (self→self is fine for testing filtering)
        cur.execute(
            """
            INSERT INTO ratings (rating_id, match_id, user1_id, user2_id, stars)
            VALUES (?, ?, ?, ?, ?)
            """,
            (rating_id_counter, match_id, uid, uid, stars)
        )
        rating_id_counter += 1

    # Now recalc aggregate
    s = sum(preset_ratings[username])
    c = len(preset_ratings[username])
    avg = float(s)/c if c else 0.0

    cur.execute(
        "UPDATE users SET rating_sum=?, rating_count=?, rating_avg=? WHERE user_id=?",
        (s, c, avg, uid)
    )

# ------------------------------------------------------------
# 4. PROFILES FOR DRIVERS
# ------------------------------------------------------------

for username, uid in driver_ids.items():
    cur.execute("SELECT 1 FROM profiles WHERE user_id=?", (uid,))
    if cur.fetchone():
        continue

    cur.execute(
        """
        INSERT INTO profiles (user_id, is_driver, area, vehicle_make, vehicle_model, vehicle_color, vehicle_plate)
        VALUES (?, 1, ?, ?, ?, ?, ?)
        """,
        (uid, "Hamra", "BMW", "320i", "Black", f"AUB-{uid:04d}")
    )

# ------------------------------------------------------------
# 5. SCHEDULES FOR DRIVERS
# ------------------------------------------------------------

for uid in driver_ids.values():
    cur.execute(
        """
        INSERT OR IGNORE INTO schedules (user_id, weekday, depart_time, direction, area)
        VALUES (?, 0, '09:00', 'to_AUB', 'Hamra')
        """,
        (uid,)
    )

# ------------------------------------------------------------
# 6. OPEN RIDE REQUESTS FOR PASSENGERS (for driver filtering)
# ------------------------------------------------------------

cur.execute("DELETE FROM ride_req")

for username, uid in pass_ids.items():
    cur.execute(
        """
        INSERT INTO ride_req (request_id, user_id, area, direction, departure_time,
                              lat, lon, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            random.randint(10_000, 99_999),
            uid,
            "Hamra",
            "to_AUB",
            "09:00",
            None,
            None,
            "open",
            time.time()
        )
    )

conn.commit()
conn.close()

print("\n=== DONE ===")
print("Passengers:")
for u in passengers:
    print(f"{u[1]}  → avg rating: {preset_ratings[u[1]]} = {sum(preset_ratings[u[1]])/(len(preset_ratings[u[1]]) or 1):.2f}")

print("\nDrivers:")
for d in drivers:
    print(f"{d[1]}  → avg rating: {preset_ratings[d[1]]} = {sum(preset_ratings[d[1]])/(len(preset_ratings[d[1]]) or 1):.2f}")

print("\nUse accounts:")
print("Passengers: p_low / p_mid / p_high / p_none    (password: pass123)")
print("Drivers:    d_low / d_mid / d_high / d_none    (password: driver123)")
