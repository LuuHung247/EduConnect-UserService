"""
User Service Application Factory
"""
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv
import os

load_dotenv()

def create_app(config_object=None):
    """
    Application factory for User Service
    Follows the same pattern as EduConnect Backend
    """
    app = Flask(__name__, static_folder=None)

    # Configure CORS with origins from environment
    cors_origins = os.getenv('CORS_ORIGINS', 'http://localhost:5173')
    CORS(app, origins=cors_origins, supports_credentials=True)

    if config_object:
        app.config.from_object(config_object)

    # Register blueprints
    from app.routes import bp as main_bp
    app.register_blueprint(main_bp)

    from app.blueprints.auth import bp as auth_bp
    from app.blueprints.users import bp as users_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)

    print("✅ User Service initialized successfully")
    print(f"📋 Registered blueprints: main, auth, users")

    return app

# Expose module-level app for gunicorn
app = create_app()
