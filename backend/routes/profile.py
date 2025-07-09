from flask import Blueprint, request, jsonify

profile_bp = Blueprint('profile', __name__)

@profile_bp.route('/', methods=['GET'])
def get_profile():
    # Mock data for frontend testing
    profile = {"name": "Jane Doe", "email": "jane@example.com"}
    return jsonify({'profile': profile})

@profile_bp.route('/update', methods=['POST'])
def update_profile():
    data = request.json
    # TODO: Update user profile
    return jsonify({'message': 'Profile updated', 'data': data})

@profile_bp.route('/resume-match', methods=['POST'])
def resume_match():
    data = request.json
    # Mock match result
    match = f"Your resume matches 2 opportunities! (Input: {data.get('resume', '')[:30]}...)"
    return jsonify({'match': match}) 