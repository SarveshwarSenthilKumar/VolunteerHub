# Script to reset the opportunities database for VolunteerHub
import sqlite3

conn = sqlite3.connect('opportunities.db')
cursor = conn.cursor()
cursor.execute("DROP TABLE IF EXISTS opportunities")
cursor.execute("DROP TABLE IF EXISTS user_opportunities")
cursor.execute('''
    CREATE TABLE opportunities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        organization_name TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        location TEXT NOT NULL,
        city TEXT NOT NULL,
        state TEXT NOT NULL,
        duration TEXT,
        volunteers_needed INTEGER,
        contact_info TEXT,
        apply_link TEXT,
        created_at TEXT NOT NULL,
        latitude REAL,
        longitude REAL
    )
''')
cursor.execute('''
    CREATE TABLE user_opportunities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        opportunity_id INTEGER NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (opportunity_id) REFERENCES opportunities(id)
    )
''')
conn.commit()
conn.close() 