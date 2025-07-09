from flask import Blueprint, request, jsonify, make_response
import sqlite3
import jwt
from datetime import datetime, timedelta
import os

auth_bp = Blueprint('auth', __name__)

# Secret key for JWT (in production, use a secure secret key)
SECRET_KEY = os.environ.get('SECRET_KEY', 'your-secret-key-here')

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.json
    username_or_phone = data.get('username')
    password = data.get('password')
    
    if not username_or_phone or not password:
        return jsonify({'error': 'Please provide username/phone and password'}), 400
    
    try:
        connection = sqlite3.connect("users.db")
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()
        
        # Allow login by username or phone number
        cursor.execute("SELECT * FROM users WHERE username = ? OR phone = ?", (username_or_phone, username_or_phone))
        user = cursor.fetchone()
        connection.close()
        
        if user and user['password'] == password:
            # Create JWT token
            token_payload = {
                'user_id': user['id'],
                'username': user['username'],
                'is_admin': bool(user['is_admin']),
                'exp': datetime.utcnow() + timedelta(days=7)  # Token expires in 7 days
            }
            token = jwt.encode(token_payload, SECRET_KEY, algorithm='HS256')
            
            # Create response with token
            response = make_response(jsonify({
                'message': 'Login successful',
                'token': token,
                'user': {
                    'id': user['id'],
                    'username': user['username'],
                    'name': user['name'],
                    'is_admin': bool(user['is_admin'])
                }
            }))
            
            # Set admin cookie if user is admin
            if user['is_admin']:
                response.set_cookie(
                    'is_admin',
                    'true',
                    max_age=7*24*60*60,  # 7 days
                    httponly=False,  # Allow JavaScript access
                    samesite='Lax'
                )
            
            return response
        else:
            return jsonify({'error': 'Invalid username/phone or password'}), 401
            
    except Exception as e:
        return jsonify({'error': f'Login error: {str(e)}'}), 500

@auth_bp.route('/signup', methods=['POST'])
def signup():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    email = data.get('email')
    name = data.get('name')
    city = data.get('city')
    state = data.get('state')
    phone = data.get('phone')
    
    if not all([username, password, email, name, city, state, phone]):
        return jsonify({'error': 'Please fill in all fields'}), 400
    
    try:
        connection = sqlite3.connect("users.db")
        cursor = connection.cursor()
        
        # Check if username already exists
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            connection.close()
            return jsonify({'error': 'Username already exists'}), 400
        
        # Check if email already exists
        cursor.execute("SELECT * FROM users WHERE emailAddress = ?", (email,))
        if cursor.fetchone():
            connection.close()
            return jsonify({'error': 'Email already registered'}), 400
        
        # Check if phone already exists
        cursor.execute("SELECT * FROM users WHERE phone = ?", (phone,))
        if cursor.fetchone():
            connection.close()
            return jsonify({'error': 'Phone number already registered'}), 400
        
        # Get current timestamp
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Insert new user
        insert_query = """
            INSERT INTO users (
                username, password, emailAddress, name, city, state, phone,
                dateJoined, saved_opportunities, is_admin
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        insert_values = (
            username, password, email, name, city, state, phone,
            current_time, '[]', 0  # Default to non-admin
        )
        cursor.execute(insert_query, insert_values)
        connection.commit()
        
        # Get the new user
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        new_user = cursor.fetchone()
        connection.close()
        
        if new_user:
            # Create JWT token for new user
            token_payload = {
                'user_id': new_user[0],  # id is first column
                'username': username,
                'is_admin': False,  # New users are not admin by default
                'exp': datetime.utcnow() + timedelta(days=7)
            }
            token = jwt.encode(token_payload, SECRET_KEY, algorithm='HS256')
            
            return jsonify({
                'message': 'Signup successful',
                'token': token,
                'user': {
                    'id': new_user[0],
                    'username': username,
                    'name': name,
                    'is_admin': False
                }
            })
        else:
            return jsonify({'error': 'Error creating user'}), 500
            
    except Exception as e:
        return jsonify({'error': f'Signup error: {str(e)}'}), 500

@auth_bp.route('/logout', methods=['POST'])
def logout():
    response = make_response(jsonify({'message': 'Logout successful'}))
    response.delete_cookie('is_admin')
    return response

@auth_bp.route('/check-admin', methods=['GET'])
def check_admin():
    """Endpoint to check if current user is admin"""
    token = request.headers.get('Authorization')
    if not token or not token.startswith('Bearer '):
        return jsonify({'is_admin': False}), 401
    
    try:
        token = token.split(' ')[1]
        payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        is_admin = payload.get('is_admin', False)
        return jsonify({'is_admin': is_admin})
    except jwt.ExpiredSignatureError:
        return jsonify({'error': 'Token expired'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'error': 'Invalid token'}), 401 