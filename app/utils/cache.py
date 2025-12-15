from flask_caching import Cache
from functools import wraps
from flask import request, make_response, g, Response
import hashlib
import json
import os

# Redis Cache config
cache = Cache()

# Key prefix - Flask-Caching tự động thêm "flask_cache_" vào đầu
# Nên key thực tế trong Redis sẽ là: flask_cache_educonnect:...
KEY_PREFIX = 'educonnect'
REDIS_KEY_PREFIX = f'flask_cache_{KEY_PREFIX}'  # Dùng cho invalidation


def init_cache(app):
    """Initialize cache with Flask app"""
    cache_config = {
        'CACHE_TYPE': 'redis',
        'CACHE_REDIS_URL': os.environ.get('REDIS_URL', 'redis://localhost:6379/0'),
        'CACHE_DEFAULT_TIMEOUT': 300,  # 5 minutes default
        # Flask-Caching tự thêm "flask_cache_" prefix
    }
    
    # Fallback to simple cache nếu không có Redis
    try:
        import redis
        r = redis.from_url(cache_config['CACHE_REDIS_URL'])
        r.ping()
        print("✅ Redis connected successfully")
    except Exception as e:
        cache_config['CACHE_TYPE'] = 'simple'
        print(f"⚠️ Redis not available ({e}), using simple cache")
    
    app.config.from_mapping(cache_config)
    cache.init_app(app)
    return cache


def _get_redis_client():
    """Get Redis client hoặc None nếu không available"""
    try:
        import redis
        r = redis.from_url(os.environ.get('REDIS_URL', 'redis://localhost:6379/0'))
        r.ping()
        return r
    except Exception:
        return None


# ============================================================
# CACHE KEY BUILDERS - Format: educonnect:{scope}:{method}:{path}:{query}
# ============================================================

def _build_cache_key(scope: str, include_user: bool = False) -> str:
    """
    Build cache key với format chuẩn.
    
    Format: educonnect:{scope}:{method}:{path}:{query}
    
    Ví dụ:
    - educonnect:public:GET:/api/v1/series:page=1
    - educonnect:user_abc123:GET:/api/v1/series/subscriptions:
    """
    method = request.method
    path = request.path
    query = request.query_string.decode('utf-8')
    
    if include_user:
        user_id = getattr(g, 'user', {}).get('userId', 'anonymous')
        scope = f"user_{user_id}"
    
    return f"{KEY_PREFIX}:{scope}:{method}:{path}:{query}"


def make_cache_key_public():
    """
    Cache key cho public endpoints.
    
    Format: educonnect:public:GET:/api/v1/series:page=1
    """
    return _build_cache_key(scope='public', include_user=False)


def make_cache_key_with_user():
    """
    Cache key cho user-specific endpoints.
    
    Format: educonnect:user_abc123:GET:/api/v1/series/subscriptions:
    """
    return _build_cache_key(scope='user', include_user=True)


# ============================================================
# ETAG SUPPORT
# ============================================================

def generate_etag(data) -> str:
    """Generate ETag from data"""
    if data is None:
        return None
    
    json_str = json.dumps(data, sort_keys=True, default=str)
    return hashlib.md5(json_str.encode()).hexdigest()


def with_etag(f):
    """Decorator: Add ETag header và check If-None-Match"""
    @wraps(f)
    def decorated(*args, **kwargs):
        response = f(*args, **kwargs)
        
        # Get response data
        if hasattr(response, 'get_json'):
            data = response.get_json()
        elif hasattr(response, 'data'):
            try:
                data = json.loads(response.data)
            except Exception:
                return response
        else:
            return response
        
        # Generate ETag
        etag = generate_etag(data)
        if not etag:
            return response
        
        # Check If-None-Match header
        if_none_match = request.headers.get('If-None-Match')
        if if_none_match and if_none_match == etag:
            return make_response('', 304)
        
        # Add ETag header
        if hasattr(response, 'headers'):
            response.headers['ETag'] = etag
            response.headers['Cache-Control'] = 'private, must-revalidate'
        
        return response
    
    return decorated


# ============================================================
# CUSTOM CACHE DECORATORS - Cache JSON data, không cache Response object
# ============================================================

def cached_public(timeout=300):
    """
    Cache decorator cho public endpoints.
    Cache JSON data thay vì Response object.
    Tự động thêm ETag header.
    
    Usage:
        @bp.route("/", methods=["GET"])
        @cached_public(timeout=300)
        def list_items():
            return _success_response(data)
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Chỉ cache GET requests
            if request.method != 'GET':
                return f(*args, **kwargs)
            
            cache_key = _build_cache_key(scope='public', include_user=False)
            
            # Try get from cache
            cached_data = cache.get(cache_key)
            if cached_data is not None:
                # Generate ETag và check If-None-Match
                etag = generate_etag(cached_data)
                if_none_match = request.headers.get('If-None-Match')
                
                if if_none_match and if_none_match == etag:
                    return Response('', status=304)
                
                # Rebuild Response từ cached JSON với ETag
                response = Response(
                    json.dumps(cached_data),
                    mimetype='application/json',
                    status=200
                )
                response.headers['ETag'] = etag
                response.headers['Cache-Control'] = 'public, must-revalidate'
                return response
            
            # Execute function
            response = f(*args, **kwargs)
            
            # Chỉ cache successful responses
            if hasattr(response, 'status_code') and response.status_code == 200:
                try:
                    if hasattr(response, 'get_json'):
                        data = response.get_json()
                    else:
                        data = json.loads(response.data)
                    
                    cache.set(cache_key, data, timeout=timeout)
                    
                    # Add ETag to response
                    etag = generate_etag(data)
                    response.headers['ETag'] = etag
                    response.headers['Cache-Control'] = 'public, must-revalidate'
                except Exception:
                    pass  # Không cache nếu không parse được
            
            return response
        
        return decorated_function
    return decorator


def cached_with_user(timeout=300):
    """
    Cache decorator cho user-specific endpoints.
    Mỗi user có cache riêng.
    Tự động thêm ETag header.
    
    Usage:
        @bp.route("/subscriptions", methods=["GET"])
        @authenticate_jwt
        @cached_with_user(timeout=120)
        def get_subscribed():
            return _success_response(data)
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Chỉ cache GET requests
            if request.method != 'GET':
                return f(*args, **kwargs)
            
            cache_key = _build_cache_key(scope='user', include_user=True)
            
            # Try get from cache
            cached_data = cache.get(cache_key)
            if cached_data is not None:
                # Generate ETag và check If-None-Match
                etag = generate_etag(cached_data)
                if_none_match = request.headers.get('If-None-Match')
                
                if if_none_match and if_none_match == etag:
                    return Response('', status=304)
                
                # Rebuild Response từ cached JSON với ETag
                response = Response(
                    json.dumps(cached_data),
                    mimetype='application/json',
                    status=200
                )
                response.headers['ETag'] = etag
                response.headers['Cache-Control'] = 'private, must-revalidate'
                return response
            
            # Execute function
            response = f(*args, **kwargs)
            
            # Chỉ cache successful responses
            if hasattr(response, 'status_code') and response.status_code == 200:
                try:
                    if hasattr(response, 'get_json'):
                        data = response.get_json()
                    else:
                        data = json.loads(response.data)
                    
                    cache.set(cache_key, data, timeout=timeout)
                    
                    # Add ETag to response
                    etag = generate_etag(data)
                    response.headers['ETag'] = etag
                    response.headers['Cache-Control'] = 'private, must-revalidate'
                except Exception:
                    pass
            
            return response
        
        return decorated_function
    return decorator


# ============================================================
# CACHE INVALIDATION - Pattern phải khớp với key format
# ============================================================

def _delete_by_pattern(pattern: str):
    """Delete all Redis keys matching pattern"""
    r = _get_redis_client()
    if r:
        deleted_count = 0
        for key in r.scan_iter(match=pattern):
            r.delete(key)
            deleted_count += 1
        return deleted_count
    else:
        # Fallback: clear all cache
        cache.clear()
        return -1


def invalidate_series_cache(serie_id: str = None):
    """
    Invalidate series related cache.
    
    Key thực tế trong Redis: flask_cache_educonnect:{scope}:{method}:{path}:{query}
    """
    r = _get_redis_client()
    
    if r:
        patterns = []
        
        # Public series endpoints
        patterns.append(f"{REDIS_KEY_PREFIX}:public:GET:/api/v1/series*")
        
        # All users' subscribed/me series
        patterns.append(f"{REDIS_KEY_PREFIX}:user_*:GET:/api/v1/series/subscriptions*")
        patterns.append(f"{REDIS_KEY_PREFIX}:user_*:GET:/api/v1/series/me*")
        
        # Specific serie
        if serie_id:
            patterns.append(f"{REDIS_KEY_PREFIX}:public:GET:/api/v1/series/{serie_id}*")
            # Lessons của serie này
            patterns.append(f"{REDIS_KEY_PREFIX}:user_*:GET:/api/v1/series/{serie_id}/lessons*")
        
        for pattern in patterns:
            _delete_by_pattern(pattern)
    else:
        cache.clear()


def invalidate_lessons_cache(series_id: str, lesson_id: str = None):
    """
    Invalidate lessons related cache.
    
    Args:
        series_id: Series ID (required)
        lesson_id: Lesson ID (optional)
    """
    r = _get_redis_client()
    
    if r:
        # Base pattern cho lessons của series này
        base_pattern = f"{REDIS_KEY_PREFIX}:user_*:GET:/api/v1/series/{series_id}/lessons"
        
        if lesson_id:
            # Invalidate specific lesson và list
            _delete_by_pattern(f"{base_pattern}/{lesson_id}*")
        
        # Always invalidate lessons list
        _delete_by_pattern(f"{base_pattern}*")
    else:
        cache.clear()


def invalidate_user_cache(user_id: str):
    """
    Invalidate all cache entries for a specific user.
    
    Args:
        user_id: User ID
    """
    pattern = f"{REDIS_KEY_PREFIX}:user_{user_id}:*"
    _delete_by_pattern(pattern)


def invalidate_all_cache():
    """Clear all educonnect cache"""
    pattern = f"{REDIS_KEY_PREFIX}:*"
    deleted = _delete_by_pattern(pattern)
    return deleted


# ============================================================
# DEBUG HELPERS
# ============================================================

def get_all_cache_keys():
    """Get all cache keys (for debugging)"""
    r = _get_redis_client()
    if r:
        return [key.decode() for key in r.scan_iter(match=f"{REDIS_KEY_PREFIX}:*")]
    return []


def get_cache_stats():
    """Get cache statistics"""
    r = _get_redis_client()
    if r:
        keys = list(r.scan_iter(match=f"{REDIS_KEY_PREFIX}:*"))
        public_keys = [k for k in keys if b':public:' in k]
        user_keys = [k for k in keys if b':user_' in k]
        
        return {
            'total_keys': len(keys),
            'public_keys': len(public_keys),
            'user_keys': len(user_keys),
            'redis_connected': True,
            'key_prefix': REDIS_KEY_PREFIX
        }
    return {'redis_connected': False}