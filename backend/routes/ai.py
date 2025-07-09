from flask import Blueprint, request, jsonify

ai_bp = Blueprint('ai', __name__)

@ai_bp.route('/generate-email', methods=['POST'])
def generate_email():
    data = request.json
    # Mock AI email for frontend testing
    email = f"Dear Volunteer,\n\nThank you for your interest! Here is a response to: '{data.get('input', '')}'\n\nBest,\nVolunteerHub Team"
    return jsonify({'email': email}) 