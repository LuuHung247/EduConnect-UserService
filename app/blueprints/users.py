from flask import Blueprint, request, jsonify, g
from app.services.user_service import (
    create_user,
    get_user_by_id,
    update_user,
    UserService
)
from app.middleware.auth import authenticate_jwt
from datetime import datetime, timezone

# API Version 1
bp = Blueprint("users", __name__, url_prefix="/api/v1/users")


def _success_response(data, message=None, status=200):
    """Helper: Create success response"""
    response = {"success": True, "data": data}
    if message:
        response["message"] = message
    return jsonify(response), status


def _error_response(message, status=500):
    """Helper: Create error response"""
    return jsonify({"success": False, "message": message}), status


@bp.route("/profile", methods=["POST"])
@authenticate_jwt
def create_profile():
    """Create user profile"""
    try:
        user_data = request.get_json() or {}
        user_id = user_data.get("userId")

        if not user_id:
            return _error_response("userId is required", 400)

        # Check if user already exists
        existing = get_user_by_id(user_id)
        if existing:
            return _error_response("User profile already exists", 409)

        result = create_user(user_data)
        return _success_response(result, "User profile created successfully", 201)

    except Exception as e:
        return _error_response(str(e))


@bp.route("/profile", methods=["GET"])
@authenticate_jwt
def get_current_profile():
    """Get current authenticated user's profile"""
    try:
        user_id = g.user_sub
        user = get_user_by_id(user_id)

        # Auto-create profile if not exists
        if not user:
            user_data = {
                "userId": user_id,
                "name": g.user_name,
                "email": g.user_email,
            }
            user = create_user(user_data)
            return _success_response(user, "User profile created automatically", 201)

        return _success_response(user)

    except Exception as e:
        print(f"Get Profile error: {str(e)}")
        return _error_response(str(e))


@bp.route("/<user_id>", methods=["GET"])
@authenticate_jwt
def get_user(user_id):
    """Get user by ID"""
    try:
        user = get_user_by_id(user_id)

        if not user:
            return _error_response("User not found", 404)

        return _success_response(user)

    except Exception as e:
        return _error_response(str(e))


@bp.route("/<user_id>", methods=["PUT"])
@authenticate_jwt
def update_user_profile(user_id):
    """Update user profile with optional avatar upload"""
    try:
        print(f"[DEBUG] Update user profile for: {user_id}")
        print(f"[DEBUG] Request content type: {request.content_type}")
        print(f"[DEBUG] Request files: {list(request.files.keys())}")
        print(f"[DEBUG] Request form: {list(request.form.keys())}")

        # Handle both JSON and multipart/form-data
        avatar_file = None
        if request.files and 'avatar' in request.files:
            avatar_file = request.files['avatar']
            print(f"[DEBUG] Avatar file found: {avatar_file.filename}")
            # Get other data from form
            data = request.form.to_dict()
            print(f"[DEBUG] Form data: {data}")
        else:
            # Regular JSON update
            data = request.get_json() or {}
            print(f"[DEBUG] JSON data: {data}")

        # Check if user exists
        existing = get_user_by_id(user_id)
        if not existing:
            return _error_response("User not found", 404)

        print(f"[DEBUG] Calling update_user with avatar_file: {avatar_file}")
        # Update user with optional avatar
        updated = update_user(user_id, data, avatar_file)
        print(f"[DEBUG] Update result - avatar field: {updated.get('avatar') if updated else 'None'}")
        return _success_response(updated, "User updated successfully")

    except Exception as e:
        print(f"[ERROR] Exception in update_user_profile: {str(e)}")
        import traceback
        traceback.print_exc()
        return _error_response(str(e))


@bp.route('/sync', methods=['POST'])
@authenticate_jwt
def sync_user():
    """Sync Cognito user with local database"""
    try:
        user_data = {
            'cognito_sub': g.user_sub,
            'email': g.user_email,
            'name': g.user_name or request.json.get('name')
        }

        additional_info = request.get_json() or {}
        user_data.update({
            'gender': additional_info.get('gender'),
            'birthdate': additional_info.get('birthdate'),
            'avatar': additional_info.get('avatar'),
        })

        synced_user, error = UserService.sync_cognito_user(user_data)

        if error:
            return jsonify({'error': error}), 400

        return jsonify({
            'success': True,
            'message': 'User synced successfully',
            'data': synced_user
        }), 200

    except Exception as e:
        print(f"Sync Error: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ========================================
# NEW ENDPOINTS FOR SUBSCRIPTION MANAGEMENT
# Used by Serie Service for inter-service communication
# ========================================

@bp.route("/<user_id>/subscriptions", methods=["GET"])
@authenticate_jwt
def get_user_subscriptions(user_id):
    """
    Get user's subscribed serie IDs
    Internal API for Serie Service
    """
    try:
        user = get_user_by_id(user_id)

        if not user:
            return _error_response("User not found", 404)

        # Return serie_subscribe array (note: typo in DB is 'serie_subcribe')
        subscriptions = user.get("serie_subcribe", []) or user.get("serie_subscribe", [])

        return _success_response({
            "user_id": user_id,
            "subscriptions": subscriptions
        })

    except Exception as e:
        return _error_response(str(e))


@bp.route("/<user_id>/subscriptions", methods=["POST"])
@authenticate_jwt
def add_subscription(user_id):
    """
    Add serie to user's subscriptions
    Called by Serie Service when user subscribes

    Request Body:
        {
            "serie_id": "64abc123..."
        }
    """
    try:
        from app.utils.mongodb import get_db

        data = request.get_json() or {}
        serie_id = data.get("serie_id")

        if not serie_id:
            return _error_response("serie_id is required", 400)

        user = get_user_by_id(user_id)
        if not user:
            return _error_response("User not found", 404)

        # Check if already subscribed
        subscriptions = user.get("serie_subcribe", [])
        if serie_id in subscriptions:
            return _error_response("Already subscribed", 409)

        # Add subscription
        _, db = get_db()
        users_collection = db["users"]

        users_collection.update_one(
            {"_id": user_id},
            {
                "$addToSet": {"serie_subcribe": serie_id},
                "$set": {"updatedAt": datetime.now(timezone.utc)}
            }
        )

        return _success_response({
            "message": "Subscription added successfully"
        })

    except Exception as e:
        return _error_response(str(e))


@bp.route("/<user_id>/subscriptions/<serie_id>", methods=["DELETE"])
@authenticate_jwt
def remove_subscription(user_id, serie_id):
    """
    Remove serie from user's subscriptions
    Called by Serie Service when user unsubscribes
    """
    try:
        from app.utils.mongodb import get_db

        user = get_user_by_id(user_id)
        if not user:
            return _error_response("User not found", 404)

        # Remove subscription
        _, db = get_db()
        users_collection = db["users"]

        users_collection.update_one(
            {"_id": user_id},
            {
                "$pull": {"serie_subcribe": serie_id},
                "$set": {"updatedAt": datetime.now(timezone.utc)}
            }
        )

        return _success_response({
            "message": "Subscription removed successfully"
        })

    except Exception as e:
        return _error_response(str(e))


@bp.route("/subscribers/<serie_id>", methods=["GET"])
@authenticate_jwt
def get_serie_subscribers(serie_id):
    """
    Get all user emails subscribed to a serie
    Used by Serie Service for sending notifications
    """
    try:
        from app.utils.mongodb import get_db

        _, db = get_db()
        users_collection = db["users"]

        # Find all users subscribed to this serie
        subscribers = users_collection.find(
            {"serie_subcribe": serie_id},
            {"email": 1, "_id": 0}
        )

        emails = [sub.get("email") for sub in subscribers if sub.get("email")]

        return _success_response({
            "serie_id": serie_id,
            "emails": emails,
            "count": len(emails)
        })

    except Exception as e:
        return _error_response(str(e))


@bp.route("/subscriptions/serie/<serie_id>", methods=["DELETE"])
@authenticate_jwt
def remove_serie_from_all_users(serie_id):
    """
    Remove serie from ALL users' subscriptions
    Called when a serie is deleted
    """
    try:
        from app.utils.mongodb import get_db

        _, db = get_db()
        users_collection = db["users"]

        # Remove from all users
        result = users_collection.update_many(
            {"serie_subcribe": serie_id},
            {
                "$pull": {"serie_subcribe": serie_id},
                "$set": {"updatedAt": datetime.now(timezone.utc)}
            }
        )

        return _success_response({
            "message": f"Serie removed from {result.modified_count} users",
            "modified_count": result.modified_count
        })

    except Exception as e:
        return _error_response(str(e))
