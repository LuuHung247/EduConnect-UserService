"""
Main blueprint for User Service
Health check and basic endpoints
"""
from flask import Blueprint, jsonify

bp = Blueprint('main', __name__)

@bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for User Service"""
    return jsonify({
        "status": "ok",
        "service": "user-service",
        "port": 5002
    }), 200
