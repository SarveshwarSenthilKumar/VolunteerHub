import sqlite3
import sys

DB_PATH = 'users.db'

def make_admin(username):
    conn = sqlite3.connect(DB_PATH)
    crsr = conn.cursor()
    crsr.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = crsr.fetchone()
    if not user:
        print(f"User '{username}' not found.")
        conn.close()
        return
    crsr.execute("UPDATE users SET is_admin = 1 WHERE username = ?", (username,))
    conn.commit()
    print(f"User '{username}' is now an admin.")
    conn.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        username = sys.argv[1]
    else:
        username = input("Enter the username to promote to admin: ").strip()
    make_admin(username) 