from sqlalchemy.orm import Session
from typing import Optional
from fastapi import HTTPException, status

from app.models.user import User
from app.schemas.user import UserUpdate, UserResponse


class UserService:
    def __init__(self, db: Session):
        self.db = db

    def get_user_profile(self, user_id: int) -> Optional[User]:
        """Get user profile by ID."""
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        return user

    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username."""
        return self.db.query(User).filter(User.username == username).first()

    def update_user_profile(self, user_id: int, user_data: UserUpdate) -> User:
        """Update user profile."""
        user = self.get_user_profile(user_id)
        
        # Check if username is being changed and if it's already taken
        if user_data.username and user_data.username != user.username:
            existing_user = self.get_user_by_username(user_data.username)
            if existing_user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Username already taken"
                )
        
        # Update fields
        if user_data.full_name is not None:
            user.full_name = user_data.full_name
        if user_data.username is not None:
            user.username = user_data.username
        
        self.db.commit()
        self.db.refresh(user)
        
        return user

    def deactivate_user(self, user_id: int) -> User:
        """Deactivate a user account."""
        user = self.get_user_profile(user_id)
        user.is_active = False
        self.db.commit()
        self.db.refresh(user)
        return user

    def activate_user(self, user_id: int) -> User:
        """Activate a user account."""
        user = self.get_user_profile(user_id)
        user.is_active = True
        self.db.commit()
        self.db.refresh(user)
        return user 