from flask import Blueprint, request, jsonify

opportunities_bp = Blueprint('opportunities', __name__)

@opportunities_bp.route('/', methods=['GET'])
def list_opportunities():
    # Mock data for frontend testing
    opportunities = [
        {"id": 1, "title": "Beach Cleanup", "description": "Help clean the local beach."},
        {"id": 2, "title": "Food Bank Volunteer", "description": "Assist at the city food bank."},
        {"id": 3, "title": "Tutoring Kids", "description": "Tutor elementary students in math and reading."}
    ]
    return jsonify({'opportunities': opportunities})

@opportunities_bp.route('/saved', methods=['GET'])
def get_saved_opportunities():
    # Mock saved opportunities
    saved = [
        {"id": 2, "title": "Food Bank Volunteer", "description": "Assist at the city food bank."}
    ]
    return jsonify({'saved': saved})

@opportunities_bp.route('/save', methods=['POST'])
def save_opportunity():
    data = request.json
    # TODO: Save opportunity for user
    return jsonify({'message': 'Opportunity saved', 'data': data})

@opportunities_bp.route('/remove', methods=['POST'])
def remove_opportunity():
    data = request.json
    # TODO: Remove saved opportunity for user
    return jsonify({'message': 'Opportunity removed', 'data': data}) 