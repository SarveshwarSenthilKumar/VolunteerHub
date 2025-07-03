import sqlite3

conn = sqlite3.connect('users.db')
cursor = conn.cursor()

# Check if 'phone' column exists
cursor.execute("PRAGMA table_info(users)")
columns = [col[1] for col in cursor.fetchall()]
if 'phone' not in columns:
    cursor.execute("ALTER TABLE users ADD COLUMN phone TEXT NOT NULL DEFAULT ''")
    print("Added 'phone' column to users table.")
else:
    print("'phone' column already exists.")

conn.commit()
conn.close() 