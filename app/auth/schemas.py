"""Pydantic schemas for authentication."""
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, validator
from app.core.config import settings


class UserRegister(BaseModel):
    """User registration schema."""
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=100)
    full_name: Optional[str] = Field(None, max_length=255)
    
    @validator("username")
    def username_alphanumeric(cls, v):
        """Validate username is alphanumeric with underscores."""
        if not v.replace("_", "").isalnum():
            raise ValueError("Username must be alphanumeric (underscores allowed)")
        return v
    
    @validator("password")
    def password_strength(cls, v):
        """Validate password strength."""
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class UserLogin(BaseModel):
    """User login schema."""
    email: EmailStr
    password: str


class Token(BaseModel):
    """Token response schema."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefresh(BaseModel):
    """Token refresh request schema."""
    refresh_token: str


class UserResponse(BaseModel):
    """User response schema."""
    id: int
    email: str
    username: str
    full_name: Optional[str]
    telegram_id: Optional[int]
    telegram_username: Optional[str] = None
    locale: str
    is_active: bool
    is_verified: bool
    is_superuser: bool
    role: str
    
    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    """User update schema."""
    full_name: Optional[str] = None
    username: Optional[str] = None
    locale: Optional[str] = None
    
    @validator("username")
    def username_alphanumeric(cls, v):
        """Validate username is alphanumeric with underscores."""
        if v and not v.replace("_", "").isalnum():
            raise ValueError("Username must be alphanumeric (underscores allowed)")
        return v

    @validator("locale")
    def valid_locale(cls, v):
        if v is not None and v not in settings.supported_locales:
            raise ValueError(f"Unsupported locale: {v}")
        return v


class LocaleUpdate(BaseModel):
    """Locale change request schema."""
    locale: str
    
    @validator("locale")
    def valid_locale(cls, v):
        if v not in settings.supported_locales:
            raise ValueError(f"Unsupported locale: {v}")
        return v


class PasswordChange(BaseModel):
    """Password change schema."""
    old_password: str
    new_password: str = Field(..., min_length=8, max_length=100)
    
    @validator("new_password")
    def password_strength(cls, v):
        """Validate password strength."""
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class EmailVerificationRequest(BaseModel):
    """Email verification request schema."""
    email: EmailStr


class EmailVerificationConfirm(BaseModel):
    """Email verification confirmation schema."""
    token: str


class PasswordResetRequest(BaseModel):
    """Password reset request schema."""
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Password reset confirmation schema."""
    token: str
    new_password: str = Field(..., min_length=8, max_length=100)
    
    @validator("new_password")
    def password_strength(cls, v):
        """Validate password strength."""
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class MessageResponse(BaseModel):
    """Generic message response schema."""
    message: str
