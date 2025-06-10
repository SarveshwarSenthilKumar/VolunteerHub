from flask import Flask, render_template, request, redirect, session, jsonify, Blueprint
from flask_session import Session
from datetime import datetime
import pytz
import sqlite3
from SarvAuth import * #Used for user authentication functions

auth_blueprint = Blueprint('auth', __name__)

@auth_blueprint.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            return render_template('auth/login.html', error='Please fill in all fields')
        
        connection = sqlite3.connect("users.db")
        connection.row_factory = sqlite3.Row
        crsr = connection.cursor()
        crsr.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = crsr.fetchone()
        connection.close()
        
        if user and password == user['password']:  # Direct password comparison
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['name'] = user['name']
            return redirect('/')
        else:
            return render_template('auth/login.html', error='Invalid username or password')
    
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
        
        if not all([username, password, email, name, city, state]):
            return render_template('auth/signup.html', error='Please fill in all fields')
        
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
        
        try:
            # Insert new user
            crsr.execute("""
                INSERT INTO users (
                    username, password, emailAddress, name, city, state, 
                    dateJoined, saved_opportunities
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                username, password, email, name, city, state,
                datetime.now(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S'),
                '[]'
            ))
            
            connection.commit()
            connection.close()
            
            # Set session after successful signup
            session['username'] = username
            session['name'] = name
            return redirect('/')
            
        except Exception as e:
            connection.close()
            return render_template('auth/signup.html', error=f'Error creating user: {str(e)}')
    
    return render_template('auth/signup.html')

@auth_blueprint.route('/logout')
def logout():
    session.clear()
    return redirect('/')
