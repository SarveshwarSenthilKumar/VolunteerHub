# Script to reset the users database for VolunteerHub
import sqlite3

conn = sqlite3.connect('users.db')
cursor = conn.cursor()
cursor.execute("DROP TABLE IF EXISTS users")
cursor.execute('''
    CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        password TEXT NOT NULL,
        emailAddress TEXT NOT NULL,
        name TEXT NOT NULL,
        city TEXT NOT NULL,
        state TEXT NOT NULL,
        phone TEXT NOT NULL,
        dateJoined TEXT NOT NULL,
        saved_opportunities TEXT DEFAULT '[]',
        is_admin INTEGER DEFAULT 0,
        resume BLOB,
        skills TEXT DEFAULT '',
        dateOfBirth TEXT
    )
''')
conn.commit()
conn.close()
print("users.db has been reset with the latest schema.") 