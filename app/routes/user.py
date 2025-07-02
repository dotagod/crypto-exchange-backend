from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from typing import Optional

from app.core.db import get_db
from app.core.security import get_current_user
from app.services.user.user_service import UserService
from app.schemas.user import UserUpdate, UserResponse

router = APIRouter(prefix="/users", tags=["users"])


def get_current_user_id(authorization: Optional[str] = Header(None)) -> int:
    """Get current user ID from JWT token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = authorization.split(" ")[1]
    username = get_current_user(token)
    
    # For now, we'll use a simple approach to get user ID
    # In a real app, you'd store user ID in the token or query the database
    db = next(get_db())
    user_service = UserService(db)
    user = user_service.get_user_by_username(username)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user.id


@router.get("/profile", response_model=UserResponse)
def get_profile(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Get current user profile."""
    user_service = UserService(db)
    user = user_service.get_user_profile(current_user_id)
    return user


@router.put("/profile", response_model=UserResponse)
def update_profile(
    user_data: UserUpdate,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Update current user profile."""
    user_service = UserService(db)
    user = user_service.update_user_profile(current_user_id, user_data)
    return user


@router.get("/{user_id}", response_model=UserResponse)
def get_user_by_id(
    user_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """Get user profile by ID (for admin purposes)."""
    # In a real app, you'd check if current_user has admin privileges
    user_service = UserService(db)
    user = user_service.get_user_profile(user_id)
    return user 