import sqlite3

def make_user_admin(username):
    """Make a user an admin by their username"""
    try:
        connection = sqlite3.connect("users.db")
        cursor = connection.cursor()
        
        # Check if user exists
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        
        if user:
            # Update user to be admin
            cursor.execute("UPDATE users SET is_admin = 1 WHERE username = ?", (username,))
            connection.commit()
            print(f"User '{username}' is now an admin!")
        else:
            print(f"User '{username}' not found.")
        
        connection.close()
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    username = input("Enter username to make admin: ")
    make_user_admin(username) 