import sqlite3

conn = sqlite3.connect(
    "database.db"
)  # Using .db file instead of :memory: for persistent storage
cursor = conn.cursor()
# Using INTEGER PRIMARY KEY for auto-incrementing IDs (user_id, request_id, etc)
cursor.execute(
    """
               CREATE TABLE users(
                   user_id INTEGER PRIMARY KEY,
                   username TEXT UNIQUE NOT NULL,
                   password TEXT NOT NULL,
                   email TEXT UNIQUE NOT NULL,
                   is_driver INTEGER DEFAULT 0,
                   area TEXT,
                   rating_avg REAL NOT NULL DEFAULT 0,
                   rating_count INTEGER NOT NULL DEFAULT 0
               )
               """
)

cursor.execute(
    """
               CREATE TABLE profiles(
                   user_id INTEGER PRIMARY KEY,
                   is_driver INTEGER NOT NULL,
                   area TEXT NOT NULL,
                   vehicle_make TEXT,
                   vehicle_model TEXT,
                   vehicle_color TEXT,
                   vehicle_plate TEXT,
                   FOREIGN KEY(user_id) REFERENCES users(user_id),
               )
               """
)

cursor.execute(
    """
               CREATE TABLE schedules(
                   sched_id INTEGER PRIMARY KEY,
                   user_id INTEGER NOT NULL,
                   day TEXT NOT NULL,
                   direction TEXT NOT NULL,
                   area TEXT NOT NULL,
                   departure_time TEXT NOT NULL,
                   FOREIGN KEY(user_id) REFERENCES users(user_id)
               )
               """
)

cursor.execute(
    """
               CREATE TABLE ride_req(
                   request_id INTEGER PRIMARY KEY,
                   user_id INTEGER NOT NULL,
                   area TEXT NOT NULL,
                   direction TEXT NOT NULL,
                   departure_time TEXT NOT NULL,
                   status TEXT NOT NULL,
                   created_at TEXT NOT NULL,
                   FOREIGN KEY(user_id) REFERENCES users(user_id)
               )
               """
)
# accept/decline
cursor.execute(
    """
               CREATE TABLE ride_decision(
                   request_id INTEGER PRIMARY KEY,
                   user_id INTEGER NOT NULL,
                   driver_id INTEGER NOT NULL,
                   status TEXT NOT NULL,
                   accepted_at TEXT,
                   declined_at TEXT,
                   FOREIGN KEY(user_id) REFERENCES users(user_id),
                   FOREIGN KEY(driver_id) REFERENCES users(user_id)
                   UNIQUE(request_id, driver_id)
               )
               """
)

cursor.execute(
    """
               CREATE TABLE matches(
                   match_id INTEGER PRIMARY KEY,
                   request_id INTEGER NOT NULL,
                   user_id INTEGER NOT NULL,
                   driver_id INTEGER NOT NULL,
                   area TEXT NOT NULL,
                   direction TEXT NOT NULL,
                   departure_time TEXT NOT NULL,
                   driver_ip TEXT,
                   driver_port INTEGER,
                   user_ip TEXT,
                   user_port INTEGER,
                   status TEXT NOT NULL,
                   created_at TEXT,
                   accepted_at TEXT,
                   cancelled_at TEXT,
                   completed_at TEXT,
                   FOREIGN KEY(request_id) REFERENCES ride_req(request_id),
                   FOREIGN KEY(user_id) REFERENCES users(user_id),
                   FOREIGN KEY(driver_id) REFERENCES users(user_id)
               )
               """
)
# unique is bc we can have only 1 rating per ride
cursor.execute(
    """
               CREATE TABLE ratings(
                   rating_id INTEGER PRIMARY KEY,
                   match_id INTEGER NOT NULL,
                   user1_id INTEGER NOT NULL,
                   user2_id INTEGER NOT NULL,
                   stars INTEGER NOT NULL,
                   comment TEXT,
                   UNIQUE(match_id, user2_id),
                   FOREIGN KEY(match_id) REFERENCES matches(match_id),
                   FOREIGN KEY(user1_id) REFERENCES users(user_id),
                   FOREIGN KEY(user2_id) REFERENCES users(user_id)
               )
               """
)
conn.commit()
conn.close()
