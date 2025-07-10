from flask import Flask, render_template, request, redirect, session, jsonify, Blueprint
from flask_session import Session
from datetime import datetime
import pytz
import sqlite3
from SarvAuth import * #Used for user authentication functions
import re

auth_blueprint = Blueprint('auth', __name__)

@auth_blueprint.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username_or_phone = request.form.get('username')
        password = request.form.get('password')
        
        if not username_or_phone or not password:
            return render_template('auth/login.html', error='Please fill in all fields')
        
        connection = sqlite3.connect("users.db")
        connection.row_factory = sqlite3.Row
        crsr = connection.cursor()
        # Allow login by username or phone number
        crsr.execute("SELECT * FROM users WHERE username = ? OR phone = ?", (username_or_phone, username_or_phone))
        user = crsr.fetchone()
        connection.close()
        
        if user and password == user['password']:
            session['user_id'] = user['id']
            session['username'] = user['username']
            if user["is_admin"] != 0:
                session["is_admin"] = user["is_admin"]
            session['name'] = user['username']
            return redirect('/')
        else:
            return render_template('auth/login.html', error='Invalid username/phone or password')
    
    return render_template('auth/login.html')

@auth_blueprint.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        email = request.form.get('email')
        name = request.form.get('name')
        city = request.form.get('city')
        state = request.form.get('state')
        phone = request.form.get('phoneNumber')
        date_of_birth = request.form.get('dateOfBirth')
        # Age validation
        if date_of_birth:
            try:
                dob = datetime.strptime(date_of_birth, '%Y-%m-%d')
                today = datetime.now()
                age = (today - dob).days // 365
                if age < 6:
                    return render_template('auth/signup.html', error='You must be at least 6 years old to sign up.')
            except Exception:
                return render_template('auth/signup.html', error='Invalid date of birth.')
        else:
            return render_template('auth/signup.html', error='Please enter your date of birth.')
        # Phone validation (simple international/US number check)
        phone_pattern = r'^(\+\d{1,3}[- ]?)?\d{10}$'
        if not phone or not re.match(phone_pattern, phone):
            return render_template('auth/signup.html', error='Please enter a valid phone number (10 digits, with optional country code).')
        if not all([username, password, email, date_of_birth, name, city, state, phone]):
            return render_template('auth/signup.html', error='Please fill in all fields')
        
        try:
            connection = sqlite3.connect("users.db")
            crsr = connection.cursor()
            # Check if username already exists
            crsr.execute("SELECT * FROM users WHERE username = ?", (username,))
            if crsr.fetchone():
                connection.close()
                return render_template('auth/signup.html', error='Username already exists')
            # Check if email already exists
            crsr.execute("SELECT * FROM users WHERE emailAddress = ?", (email,))
            if crsr.fetchone():
                connection.close()
                return render_template('auth/signup.html', error='Email already registered')
            # Check if phone already exists
            crsr.execute("SELECT * FROM users WHERE phone = ?", (phone,))
            if crsr.fetchone():
                connection.close()
                return render_template('auth/signup.html', error='Phone number already registered')
            # Get current timestamp
            current_time = datetime.now(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')
            # Insert new user
            insert_query = """
                INSERT INTO users (
                    username, password, emailAddress, dateOfBirth, name, city, state, phone,
                    dateJoined, saved_opportunities
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            insert_values = (
                username, password, email, date_of_birth, name, city, state, phone,
                current_time, '[]'
            )
            crsr.execute(insert_query, insert_values)
            connection.commit()
            # Verify the user was created
            crsr.execute("SELECT * FROM users WHERE username = ?", (username,))
            new_user = crsr.fetchone()
            if new_user:
                # Set session after successful signup
                session['username'] = username
                session['name'] = username
                connection.close()
                return redirect('/')
            else:
                connection.close()
                return render_template('auth/signup.html', error='Error creating user: User not found after creation')
        except Exception as e:
            if 'connection' in locals():
                connection.close()
            return render_template('auth/signup.html', error=f'Error creating user: {str(e)}')
    return render_template('auth/signup.html')

@auth_blueprint.route('/logout')
def logout():
    session.clear()
    return redirect('/')
