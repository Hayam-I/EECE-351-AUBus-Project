import sqlite3

DB_PATH = "database.db"   # same as in server main.py

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# 3 passengers (is_driver = 0)
passengers = [
    ("Passenger One",   "pass1", "pass123", "p1@example.com", 0, "Hamra"),
    ("Passenger Two",   "pass2", "pass123", "p2@example.com", 0, "Hamra"),
    ("Passenger Three", "pass3", "pass123", "p3@example.com", 0, "Hamra"),
]

# 3 drivers (is_driver = 1)
drivers = [
    ("Driver One",   "driver1", "driver123", "d1@example.com", 1, "Hamra"),
    ("Driver Two",   "driver2", "driver123", "d2@example.com", 1, "Hamra"),
    ("Driver Three", "driver3", "driver123", "d3@example.com", 1, "Hamra"),
]

# Insert users; OR IGNORE so you can re-run without crashing
cur.executemany(
    """
    INSERT OR IGNORE INTO users (name, username, password, email, is_driver, area)
    VALUES (?, ?, ?, ?, ?, ?)
    """,
    passengers + drivers,
)

# Look up driver user_ids
driver_usernames = [d[1] for d in drivers]  # ["d1","d2","d3"]
cur.execute(
    f"""
    SELECT user_id, username
    FROM users
    WHERE username IN ({",".join("?" for _ in driver_usernames)})
    """,
    driver_usernames,
)
driver_rows = cur.fetchall()  # list of (user_id, username)

# Create simple profiles for drivers (only if they don't already exist)
for user_id, username in driver_rows:
    cur.execute("SELECT 1 FROM profiles WHERE user_id=?", (user_id,))
    if cur.fetchone():
        continue  # profile already exists

    cur.execute(
        """
        INSERT INTO profiles (user_id, is_driver, area, vehicle_make, vehicle_model, vehicle_color, vehicle_plate)
        VALUES (?, 1, ?, ?, ?, ?, ?)
        """,
        (user_id, "Hamra", "Toyota", "Corolla", "White", f"AUB-{user_id:04d}"),
    )

    # Also make sure users.is_driver = 1 (in case it changed)
    cur.execute("UPDATE users SET is_driver=1 WHERE user_id=?", (user_id,))

# Give each driver one schedule slot so they show up for matching
# Example: weekday=0 (Monday), 09:00, to_AUB, area="Hamra"
for user_id, username in driver_rows:
    cur.execute(
        """
        INSERT OR IGNORE INTO schedules (user_id, weekday, depart_time, direction, area)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, 0, "09:00", "to_AUB", "Hamra"),
    )

conn.commit()
conn.close()

print("Seed complete. Users:")
print("  Passengers: pass1/pass2/pass3  (password: pass123)")
print("  Drivers:    driver1/driver2/driver3  (password: driver123)")
