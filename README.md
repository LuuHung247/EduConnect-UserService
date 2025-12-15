# User Service - EduConnect Microservice

User management microservice extracted from EduConnect monolithic backend.

## Overview

User Service handles all user-related operations including:
- User profile management (CRUD)
- JWT authentication & verification
- User subscriptions to series
- Integration with AWS Cognito

## Architecture

```
Frontend → Backend (API Gateway) → User Service → MongoDB
                                    ↓
                              AWS Cognito (JWT)
```

## Endpoints

### Authentication
- `POST /api/v1/auth/verify` - Verify JWT token

### User Profile
- `POST /api/v1/users/profile` - Create user profile
- `GET /api/v1/users/profile` - Get current user profile
- `GET /api/v1/users/{user_id}` - Get user by ID
- `PUT /api/v1/users/{user_id}` - Update user profile (supports avatar upload)
- `POST /api/v1/users/sync` - Sync Cognito user

### Subscriptions (Internal APIs)
- `GET /api/v1/users/{user_id}/subscriptions` - Get user's subscriptions
- `POST /api/v1/users/{user_id}/subscriptions` - Add subscription
- `DELETE /api/v1/users/{user_id}/subscriptions/{serie_id}` - Remove subscription
- `GET /api/v1/users/subscribers/{serie_id}` - Get all subscribers
- `DELETE /api/v1/users/subscriptions/serie/{serie_id}` - Remove serie from all users

## Running Locally

### Prerequisites
- Python 3.11+
- MongoDB
- AWS Cognito credentials

### Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure environment:
```bash
cp .env.example .env
# Edit .env with your MongoDB URI and Cognito config
```

3. Run:
```bash
python3 app.py
```

Service runs on http://localhost:5002

## Running with Docker

```bash
docker build -t user-service .
docker run -p 5002:5002 --env-file .env user-service
```

## Running with Docker Compose

See main docker-compose.yml in project root:
```bash
docker-compose up user-service
```

## Health Check

```bash
curl http://localhost:5002/health
```

Response:
```json
{
  "status": "ok",
  "service": "user-service",
  "port": 5002
}
```

## Avatar Upload

The User Service integrates with Media Service for avatar uploads:

```bash
# Using multipart/form-data
curl -X PUT http://localhost:5002/api/v1/users/{user_id} \
  -H "Authorization: Bearer {token}" \
  -F "avatar=@/path/to/image.jpg" \
  -F "name=John Doe" \
  -F "bio=Updated bio"

# Using JSON (no avatar upload)
curl -X PUT http://localhost:5002/api/v1/users/{user_id} \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{"name": "John Doe", "bio": "Updated bio"}'
```

Features:
- Automatically deletes old avatar when uploading new one
- Supports both multipart/form-data (with file) and JSON (without file)
- Uses Media Service for S3 storage

## Configuration

Environment variables (see `.env.example`):

- `PORT` - Service port (default: 5002)
- `MONGODB_URI` - MongoDB connection string
- `MONGODB_NAME` - Database name
- `COGNITO_USER_POOL_ID` - AWS Cognito User Pool ID
- `COGNITO_APP_CLIENT_ID` - AWS Cognito App Client ID
- `AWS_REGION` - AWS region (default: ap-southeast-1)
- `MEDIA_SERVICE_URL` - Media Service URL (default: http://localhost:8001)

## Technology Stack

- **Framework**: Flask 3.0
- **Server**: Gunicorn
- **Database**: MongoDB (PyMongo 4.6)
- **Authentication**: AWS Cognito (PyJWT, python-jose)
- **Caching**: Redis (optional)
- **CORS**: Flask-CORS

## Development

Pattern follows the same structure as EduConnect Backend:
- **Blueprints**: Route handlers
- **Services**: Business logic
- **Middleware**: Authentication
- **Utils**: Shared utilities

## Security

- JWT verification with AWS Cognito
- Non-root user in Docker
- Input validation
- CORS configured
