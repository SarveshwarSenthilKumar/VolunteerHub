import os
from datetime import datetime
import pytz
import sqlite3

def create_opportunities_database():
    # Create opportunities database
    connection = sqlite3.connect("opportunities.db")
    crsr = connection.cursor()
    
    # Drop existing tables if they exist
    crsr.execute("DROP TABLE IF EXISTS opportunities")
    crsr.execute("DROP TABLE IF EXISTS user_opportunities")
    
    # Create opportunities table
    crsr.execute("""
        CREATE TABLE opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_name TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            location TEXT NOT NULL,
            city TEXT NOT NULL,
            state TEXT NOT NULL,
            contact_info TEXT,
            website TEXT,
            created_at TEXT NOT NULL,
            latitude REAL,
            longitude REAL
        )
    """)
    
    # Create user_opportunities table for tracking user interactions
    crsr.execute("""
        CREATE TABLE user_opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            opportunity_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (opportunity_id) REFERENCES opportunities(id)
        )
    """)
    
    connection.commit()
    crsr.close()
    connection.close()
    print("Opportunities database created successfully!")

def create_users_database():
    # Create users database
    connection = sqlite3.connect("users.db")
    crsr = connection.cursor()
    
    # Drop existing tables if they exist
    crsr.execute("DROP TABLE IF EXISTS users")
    
    # Create users table with all fields
    crsr.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            password TEXT NOT NULL,
            dateJoined TEXT,
            salt TEXT,
            accountStatus TEXT,
            role TEXT,
            twoFactorAuth TEXT,
            lastLogin TEXT,
            email TEXT,
            phoneNumber TEXT,
            name TEXT,
            dateOfBirth TEXT,
            gender TEXT,
            latitude REAL,
            longitude REAL,
            city TEXT,
            state TEXT,
            saved_opportunities TEXT DEFAULT '[]'
        )
    """)
    
    connection.commit()
    crsr.close()
    connection.close()
    print("Users database created successfully!")

if __name__ == "__main__":
    create_users_database()
    create_opportunities_database() 