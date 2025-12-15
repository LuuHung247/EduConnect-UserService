"""
Flask JWT Authentication for AWS Cognito
Supports both ID tokens and Access tokens
"""

from functools import wraps
from flask import request, g, jsonify, current_app
import os
import requests
import jwt
from jwt import PyJWKClient
from jose import jwt, jwk
from jose.utils import base64url_decode
from typing import Optional, Dict, Any
from datetime import datetime

from app.services.user_service import get_user_by_id

AWS_REGION = os.getenv('AWS_REGION', 'ap-southeast-1')
USER_POOL_ID = os.getenv('COGNITO_USER_POOL_ID')
APP_CLIENT_ID = os.getenv('COGNITO_APP_CLIENT_ID')

COGNITO_JWKS_URL = f"https://cognito-idp.{AWS_REGION}.amazonaws.com/{USER_POOL_ID}/.well-known/jwks.json"

# Cache cho JWKS
_JWKS_CACHE = {"keys": None, "fetched_at": None, "jwks_client": None}


def _get_config(key: str, default=None):
    """Get config from Flask app.config hoặc environment variables"""
    try:
        return current_app.config.get(key, os.getenv(key, default))
    except RuntimeError:
        return os.getenv(key, default)


def _get_jwks_url() -> Optional[str]:
    """Get JWKS URL from config hoặc construct từ pool ID + region"""
    jwks_url = _get_config('COGNITO_JWKS_URL') or _get_config('JWKS_URL')
    if jwks_url:
        return jwks_url
    
    pool_id = _get_config('COGNITO_USER_POOL_ID') or _get_config('COGNITO_POOL_ID')
    region = _get_config('COGNITO_REGION') or _get_config('AWS_REGION', 'ap-southeast-1')
    
    if pool_id and region:
        return f"https://cognito-idp.{region}.amazonaws.com/{pool_id}/.well-known/jwks.json"
    
    return None


def _get_issuer() -> Optional[str]:
    """Get expected issuer"""
    issuer = _get_config('JWT_ISSUER') or _get_config('COGNITO_ISSUER')
    if issuer:
        return issuer
    
    pool_id = _get_config('COGNITO_USER_POOL_ID') or _get_config('COGNITO_POOL_ID')
    region = _get_config('COGNITO_REGION') or _get_config('AWS_REGION', 'ap-southeast-1')
    
    if pool_id and region:
        return f"https://cognito-idp.{region}.amazonaws.com/{pool_id}"
    
    return None


def _get_jwks_client() -> Optional[PyJWKClient]:
    """Get or create PyJWKClient"""
    if _JWKS_CACHE['jwks_client'] is not None:
        return _JWKS_CACHE['jwks_client']
    
    jwks_url = _get_jwks_url()
    if not jwks_url:
        return None
    
    try:
        cache_ttl = int(_get_config('JWKS_CACHE_TTL', '86400'))
        client = PyJWKClient(jwks_url, cache_keys=True, lifespan=cache_ttl)
        _JWKS_CACHE['jwks_client'] = client
        return client
    except Exception as e:
        try:
            current_app.logger.error(f"Failed to create JWKS client: {e}")
        except RuntimeError:
            print(f"Failed to create JWKS client: {e}")
        return None


def _extract_token() -> Optional[str]:
    """Extract token from Authorization header"""
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None
    return auth_header[7:]


def _verify_token(token: str) -> Dict[str, Any]:
    """Verify and decode JWT token"""
    # Get unverified header để extract kid
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as e:
        raise jwt.InvalidTokenError(f'Invalid token header: {e}')
    
    kid = header.get('kid')
    if not kid:
        raise jwt.InvalidTokenError('Token missing kid in header')
    
    # Get JWKS client
    jwks_client = _get_jwks_client()
    if not jwks_client:
        raise jwt.InvalidTokenError('JWKS client not available')
    
    # Get signing key
    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
    except Exception as e:
        try:
            current_app.logger.error(f"Failed to get signing key: {e}")
        except RuntimeError:
            print(f"Failed to get signing key: {e}")
        raise jwt.InvalidTokenError(f'Failed to get signing key: {e}')
    
    # Decode unverified để check token_use
    try:
        unverified_payload = jwt.decode(token, options={'verify_signature': False})
    except Exception:
        unverified_payload = {}
    
    token_use = unverified_payload.get('token_use')
    
    # Prepare decode options
    decode_options = {
        'algorithms': ['RS256'],
        'leeway': int(_get_config('JWT_LEEWAY', '0'))
    }
    
    # Issuer validation (always required)
    issuer = _get_issuer()
    if issuer:
        decode_options['issuer'] = issuer
    
    # Audience validation - chỉ cho ID token
    # Access token không có aud claim, chỉ có client_id
    app_client_id = _get_config('COGNITO_APP_CLIENT_ID')
    
    if token_use == 'id':
        # ID token MUST have audience
        if app_client_id:
            decode_options['audience'] = app_client_id
        else:
            decode_options['options'] = {'verify_aud': False}
    else:
        # Access token - skip audience verification
        decode_options['options'] = {'verify_aud': False}
    
    # Verify and decode
    try:
        payload = jwt.decode(token, key=signing_key.key, **decode_options)
    except jwt.exceptions.MissingRequiredClaimError as e:
        # If missing aud for access token, that's okay
        if 'aud' in str(e) and token_use == 'access':
            decode_options['options'] = {'verify_aud': False}
            payload = jwt.decode(token, key=signing_key.key, **decode_options)
        else:
            raise
    
    # Validate client_id for access tokens
    if token_use == 'access' and app_client_id:
        token_client_id = payload.get('client_id')
        if token_client_id and token_client_id != app_client_id:
            raise jwt.InvalidAudienceError('Token client_id mismatch')
    
    # Validate token_use claim
    if token_use and token_use not in ('id', 'access'):
        raise jwt.InvalidTokenError(f'Invalid token_use: {token_use}')
    
    return payload


def _build_user_object(token: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Build user object from token payload"""
    return {
        'id_token': token,
        'userId': payload.get('sub'),
        'email': payload.get('email'),
        'email_verified': payload.get('email_verified'),
        'username': payload.get('preferred_username') or payload.get('cognito:username') or payload.get('username'),
        'name': payload.get('name'),
        'given_name': payload.get('given_name'),
        'family_name': payload.get('family_name'),
        'gender': payload.get('gender'),
        'birthdate': payload.get('birthdate'),
        'phone_number': payload.get('phone_number'),
        'phone_number_verified': payload.get('phone_number_verified'),
        'groups': payload.get('cognito:groups', []),
        'token_use': payload.get('token_use'),
        'auth_time': payload.get('auth_time'),
        'exp': payload.get('exp'),
        'iat': payload.get('iat'),
        'client_id': payload.get('client_id'),
        'cognito': payload
    }


def authenticate_jwt(f):
    """
    Decorator để protect Flask routes với JWT authentication từ AWS Cognito
    Supports cả ID tokens và Access tokens
    
    Configuration (via app.config hoặc environment variables):
      - COGNITO_USER_POOL_ID: Required - Cognito User Pool ID
      - COGNITO_APP_CLIENT_ID: Required - Cognito App Client ID
      - COGNITO_REGION hoặc AWS_REGION: Region (default: ap-southeast-1)
      - COGNITO_JWKS_URL: Optional - Explicit JWKS URL
      - JWKS_CACHE_TTL: Optional - Cache TTL in seconds (default: 86400)
      - JWT_LEEWAY: Optional - Leeway for token expiration (default: 0)
      - ALLOW_INSECURE_JWT: Optional - Allow insecure mode for dev (default: false)
    
    Usage:
        from auth import authenticate_jwt
        
        @app.route('/api/protected')
        @authenticate_jwt
        def protected_route():
            return jsonify({
                'user_id': g.user['user_id'],
                'email': g.user['email']
            })
    
    Token types:
        - ID Token: Contains user profile info (email, name, etc.)
        - Access Token: Contains client_id, scope, but minimal user info
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
        
        if not token:
            return jsonify({"message": "Token is missing"}), 401

        try:
            # 1. Lấy Key từ Cognito
            jwks = requests.get(COGNITO_JWKS_URL).json()

            # 2. Decode header token
            header = jwt.get_unverified_header(token)

            pem_key = None

            for key in jwks['keys']:
                if key['kid'] == header['kid']:
                    pem_key = jwk.construct(key).to_pem()
                    break
            
            if pem_key:
                print(f"DEBUG: Verifying token with Audience (Client ID): {APP_CLIENT_ID}")

                # 3. Verify Token
                payload = jwt.decode(
                    token,
                    pem_key,
                    algorithms=['RS256'],
                    audience=APP_CLIENT_ID, # Verify client id
                    issuer=f"https://cognito-idp.{AWS_REGION}.amazonaws.com/{USER_POOL_ID}",
                    options={'verify_at_hash': False}
                )
                
                # Lưu thông tin user vào context request
                g.user_sub = payload['sub'] # ID
                g.user_email = payload.get('email')
                g.user_name = payload.get('name') or payload.get('cognito:username')
                user_in_db = get_user_by_id(g.user_sub)

                if user_in_db:
                    g.user_role = user_in_db.get('role', 'student')
                else:
                    g.user_role = 'student'
            else:
                 return jsonify({"message": "Unable to find appropriate key"}), 401

        except jwt.ExpiredSignatureError:
            return jsonify({"message": "Token expired"}), 401
        except jwt.JWTClaimsError as e:
            print(f"DEBUG: Claims Error: {str(e)}")
            return jsonify({"message": f"Invalid claims: {str(e)}"}), 401
        except Exception as e:
            return jsonify({"message": f"Invalid token: {str(e)}"}), 401

        return f(*args, **kwargs)
    return decorated_function

def instructor_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not hasattr(g, 'user_role'):
            return jsonify({"message": "Authentication required first"}), 401
            
        if g.user_role not in ['instructor', 'admin']:
            return jsonify({
                "success": False,
                "message": "Permission denied. Instructor role required."
            }), 403
            
        return f(*args, **kwargs)
    return decorated_function