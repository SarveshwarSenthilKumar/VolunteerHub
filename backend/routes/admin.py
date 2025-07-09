from flask import Blueprint, request, jsonify

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