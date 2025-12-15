"""
Authentication endpoints for inter-service communication
Allows other services (Backend) to verify JWT tokens
"""
from flask import Blueprint, request, jsonify, g
from app.middleware.auth import authenticate_jwt
from app.services.user_service import get_user_by_id

bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


def _success_response(data, message=None, status=200):
    """Helper: Create success response"""
    response = {"success": True, "data": data}
    if message:
        response["message"] = message
    return jsonify(response), status


def _error_response(message, status=500):
    """Helper: Create error response"""
    return jsonify({"success": False, "message": message}), status


@bp.route("/verify", methods=["POST"])
@authenticate_jwt
def verify_jwt():
    """
    Verify JWT token and return user context
    Used by Backend and other services to authenticate requests

    Request:
        Headers:
            Authorization: Bearer <token>

    Response:
        {
            "success": true,
            "data": {
                "user_id": "cognito-sub-xxx",
                "email": "user@example.com",
                "name": "John Doe",
                "role": "student"
            }
        }
    """
    try:
        user_id = g.user_sub
        email = g.user_email
        name = g.user_name

        # Get user role from database
        user = get_user_by_id(user_id)
        role = user.get('role', 'student') if user else 'student'

        return _success_response({
            "user_id": user_id,
            "email": email,
            "name": name,
            "role": role
        })

    except Exception as e:
        return _error_response(f"Token verification failed: {str(e)}", 401)
