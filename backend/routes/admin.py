from flask import Blueprint, request, jsonify, session
import sqlite3
import os

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/dashboard', methods=['GET'])
def dashboard():
    # Mock data for frontend testing
    dashboard = {"total_users": 42, "total_opportunities": 7}
    return jsonify({'dashboard': dashboard})

@admin_bp.route('/add-opportunity', methods=['POST'])
def add_opportunity():
    data = request.json
    # TODO: Add new opportunity
    return jsonify({'message': 'Opportunity added', 'data': data})

@admin_bp.route('/delete-opportunity', methods=['POST'])
def delete_opportunity():
    data = request.json
    # TODO: Delete opportunity
    return jsonify({'message': 'Opportunity deleted', 'data': data})

@admin_bp.route('/users', methods=['GET'])
def list_users():
    # TODO: List all users
    return jsonify({'message': 'List of users'})

@admin_bp.route('/reset-opportunities-db', methods=['POST'])
def reset_opportunities_db():
    # Check if user is sarveshwarsenthilkumar
    if session.get('name') != 'sarveshwarsenthilkumar':
        return jsonify({'success': False, 'error': 'Unauthorized access'}), 403
    
    try:
        # Delete the opportunities database file
        if os.path.exists('opportunities.db'):
            os.remove('opportunities.db')
        
        # Recreate the database with the original schema
        conn = sqlite3.connect('opportunities.db')
        cursor = conn.cursor()
        
        # Create the opportunities table
        cursor.execute('''
            CREATE TABLE opportunities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                organization TEXT NOT NULL,
                location TEXT NOT NULL,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                category TEXT NOT NULL,
                requirements TEXT,
                contact_email TEXT,
                contact_phone TEXT,
                image_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Opportunities database reset successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'Database reset failed: {str(e)}'}), 500

@admin_bp.route('/reset-users-db', methods=['POST'])
def reset_users_db():
    # Check if user is sarveshwarsenthilkumar
    if session.get('name') != 'sarveshwarsenthilkumar':
        return jsonify({'success': False, 'error': 'Unauthorized access'}), 403
    
    try:
        # Delete the users database file
        if os.path.exists('users.db'):
            os.remove('users.db')
        
        # Recreate the database with the original schema
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        
        # Create the users table
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
                birthday TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Users database reset successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'Database reset failed: {str(e)}'}), 500 