from flask import Flask
from flask_cors import CORS
from routes.auth import auth_bp
from routes.opportunities import opportunities_bp
from routes.profile import profile_bp
from routes.admin import admin_bp
from routes.ai import ai_bp

app = Flask(__name__)
CORS(app)

# Register blueprints
app.register_blueprint(auth_bp, url_prefix='/api/auth')
app.register_blueprint(opportunities_bp, url_prefix='/api/opportunities')
app.register_blueprint(profile_bp, url_prefix='/api/profile')
app.register_blueprint(admin_bp, url_prefix='/api/admin')
app.register_blueprint(ai_bp, url_prefix='/api/ai')

@app.route('/')
def index():
    return {'message': 'VolunteerHub API is running.'}

if __name__ == '__main__':
    app.run(debug=True) 