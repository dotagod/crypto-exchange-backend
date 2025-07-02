# Crypto Exchange Backend API

A production-grade crypto exchange backend built with FastAPI, SQLAlchemy, and JWT authentication.

## Features

- **Authentication**: JWT-based user registration and login
- **User Management**: Profile management and user operations
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Caching**: Redis for session management
- **Documentation**: Auto-generated Swagger/OpenAPI docs
- **Docker**: Containerized development environment

## Project Structure

```
/app
  /core            → Database, security, and configuration
  /models          → SQLAlchemy models
  /schemas         → Pydantic schemas for API I/O
  /services        → Business logic
    /auth          → Authentication service
    /user          → User management service
  /routes          → FastAPI routers
  /tasks           → Celery background tasks
  /utils           → Helper functions
```

## Quick Start

### Prerequisites

- Python 3.9+
- Docker and Docker Compose
- PostgreSQL (via Docker)
- Redis (via Docker)

### Setup

1. **Clone and navigate to the project:**
   ```bash
   cd crypto_exchange_backend
   ```

2. **Copy environment file:**
   ```bash
   cp env.example .env
   ```

3. **Start the services with Docker Compose:**
   ```bash
   docker-compose up -d
   ```

4. **Access the API:**
   - API: http://localhost:8000
   - Swagger Docs: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

### Development Setup

1. **Create virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application:**
   ```bash
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

## API Endpoints

### Authentication

#### Register User
```http
POST /api/v1/auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "username": "username",
  "password": "password123",
  "full_name": "John Doe"
}
```

#### Login User
```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password123"
}
```

Response:
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer"
}
```

### User Management

#### Get Profile
```http
GET /api/v1/users/profile
Authorization: Bearer <access_token>
```

#### Update Profile
```http
PUT /api/v1/users/profile
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "full_name": "John Smith",
  "username": "newusername"
}
```

#### Get User by ID
```http
GET /api/v1/users/{user_id}
Authorization: Bearer <access_token>
```

## Database Schema

### Users Table
- `id`: Primary key
- `email`: Unique email address
- `username`: Unique username
- `hashed_password`: Bcrypt hashed password
- `full_name`: User's full name
- `is_active`: Account status
- `is_verified`: Email verification status
- `created_at`: Account creation timestamp
- `updated_at`: Last update timestamp

## Security Features

- **Password Hashing**: Bcrypt with salt
- **JWT Tokens**: Secure token-based authentication
- **CORS**: Configured for development
- **Input Validation**: Pydantic schemas
- **Error Handling**: Proper HTTP status codes

## Development

### Adding New Services

1. Create service directory in `/app/services/`
2. Add business logic in service files
3. Create schemas in `/app/schemas/`
4. Add routes in `/app/routes/`
5. Include router in `main.py`

### Database Migrations

The current setup uses SQLAlchemy's `create_all()` for simplicity. For production, consider using Alembic for database migrations.

### Environment Variables

Key environment variables:
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection string
- `SECRET_KEY`: JWT secret key
- `ACCESS_TOKEN_EXPIRE_MINUTES`: Token expiration time

## Production Considerations

- Use environment-specific configuration
- Implement proper logging
- Add rate limiting
- Set up monitoring and health checks
- Use HTTPS in production
- Implement proper error handling
- Add database migrations
- Set up CI/CD pipeline

## License

MIT License 