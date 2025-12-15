#!/usr/bin/env python3
"""
User Service - Entry Point
EduConnect User Microservice
Handles user management, authentication, and subscription operations
"""
import os
from app import app

if __name__ == '__main__':
    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5002))  # User Service runs on port 5002
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() in ['true', '1', 'yes']

    print(f"🚀 Starting User Service on {host}:{port}")
    print(f"📝 Debug mode: {debug}")

    app.run(host=host, port=port, debug=debug)
