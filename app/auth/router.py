"""Authentication router."""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import hmac
import hashlib
import logging
from urllib.parse import urlencode
from app.core.database import get_db
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_token_type,
    create_email_verification_token,
    create_password_reset_token,
    decode_email_verification_token,
    decode_password_reset_token,
)
from app.auth.schemas import (
    UserRegister,
    UserLogin,
    Token,
    TokenRefresh,
    UserResponse,
    UserUpdate,
    PasswordChange,
    LocaleUpdate,
    EmailVerificationRequest,
    EmailVerificationConfirm,
    PasswordResetRequest,
    PasswordResetConfirm,
    MessageResponse,
)
from app.auth.dependencies import get_current_user, get_current_active_user
from app.models.user import User
from app.models.organization import Organization
from app.models.billing import BillingAccount, SubscriptionPlan, SubscriptionStatus
from app.core.config import settings


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserRegister,
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Register a new user.
    
    Args:
        user_data: User registration data
        db: Database session
        
    Returns:
        Created user
        
    Raises:
        HTTPException: If email or username already exists
    """
    # Check if email exists
    result = await db.execute(select(User).where(User.email == user_data.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    
    # Check if username exists
    result = await db.execute(select(User).where(User.username == user_data.username))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken",
        )
    
    # Create new user
    user = User(
        email=user_data.email,
        username=user_data.username,
        hashed_password=get_password_hash(user_data.password),
        full_name=user_data.full_name,
    )
    
    db.add(user)
    await db.flush()  # Flush to get user.id
    
    # Create organization for the user
    org = Organization(
        name=f"{user.username}'s Organization",
        slug=f"{user.username}-org".lower(),
        description=f"Personal organization for {user.username}"
    )
    db.add(org)
    await db.flush()
    
    # Assign user to organization
    user.organization_id = org.id
    
    # Find or create "Free Trial" plan
    free_trial_plan_result = await db.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.name == "Free Trial")
    )
    free_trial_plan = free_trial_plan_result.scalar_one_or_none()
    
    if not free_trial_plan:
        # Create default Free Trial plan if doesn't exist
        from app.models.billing import SubscriptionInterval
        free_trial_plan = SubscriptionPlan(
            name="Free Trial",
            interval=SubscriptionInterval.MONTHLY,
            price=0.00,
            currency="USD",
            max_requests_per_interval=0,  # After free requests - block
            max_tokens_per_request=2000,
            free_requests_limit=10,  # 10 free requests
            free_trial_days=0,
            has_api_access=False,
            has_priority_support=False,
            has_advanced_analytics=False
        )
        db.add(free_trial_plan)
        await db.flush()
    
    # Create billing account with Free Trial plan
    billing_account = BillingAccount(
        organization_id=org.id,
        subscription_plan_id=free_trial_plan.id,
        subscription_status=SubscriptionStatus.TRIALING,
        free_requests_used=0,
        requests_used_current_period=0,
        trial_started_at=datetime.utcnow(),
        period_started_at=datetime.utcnow()
    )
    db.add(billing_account)
    
    await db.commit()
    await db.refresh(user)
    
    logger.info(f"New user registered: {user.email} with Free Trial plan (org_id={org.id})")
    
    return user


@router.post("/login", response_model=Token)
async def login(
    credentials: UserLogin,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """
    Login with email and password.
    
    Args:
        credentials: Login credentials
        db: Database session
        
    Returns:
        Access and refresh tokens
        
    Raises:
        HTTPException: If credentials are invalid
    """
    # Get user by email
    result = await db.execute(select(User).where(User.email == credentials.email))
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )
    
    # Update last login
    user.last_login_at = datetime.utcnow()
    await db.commit()
    
    # Create tokens
    access_token = create_access_token(data={"sub": user.id})
    refresh_token = create_refresh_token(data={"sub": user.id})
    
    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/refresh", response_model=Token)
async def refresh_token(
    token_data: TokenRefresh,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """
    Refresh access token using refresh token.
    
    Args:
        token_data: Refresh token
        db: Database session
        
    Returns:
        New access and refresh tokens
        
    Raises:
        HTTPException: If refresh token is invalid
    """
    payload = decode_token(token_data.refresh_token)
    verify_token_type(payload, "refresh")
    
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )
    
    # Verify user exists and is active
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    
    # Create new tokens
    access_token = create_access_token(data={"sub": user.id})
    refresh_token = create_refresh_token(data={"sub": user.id})
    
    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    current_user: User = Depends(get_current_user),
):
    """
    Logout current user.
    
    Note: With JWT, actual logout is handled client-side by removing tokens.
    This endpoint is provided for consistency and future token blacklist implementation.
    """
    # In a production system, you might want to:
    # 1. Add token to a blacklist in Redis
    # 2. Clear any server-side sessions
    # 3. Log the logout event
    return None


@router.get("/profile", response_model=UserResponse)
async def get_profile(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """
    Get current user profile.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        User profile
    """
    return current_user


@router.put("/profile", response_model=UserResponse)
async def update_profile(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Update current user profile.
    
    Args:
        user_update: Profile update data
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Updated user profile
        
    Raises:
        HTTPException: If username already taken
    """
    # Check if username is being changed and is available
    if user_update.username and user_update.username != current_user.username:
        result = await db.execute(
            select(User).where(User.username == user_update.username)
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken",
            )
        current_user.username = user_update.username
    
    # Update fields
    if user_update.full_name is not None:
        current_user.full_name = user_update.full_name
    if user_update.locale is not None:
        if user_update.locale not in settings.supported_locales:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported locale",
            )
        current_user.locale = user_update.locale
    
    current_user.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(current_user)
    
    return current_user


@router.put("/locale", response_model=UserResponse)
async def change_locale(
    payload: LocaleUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Change current user's locale."""
    if payload.locale not in settings.supported_locales:
        raise HTTPException(status_code=400, detail="Unsupported locale")
    current_user.locale = payload.locale
    current_user.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Change user password.
    
    Args:
        password_data: Old and new passwords
        current_user: Current authenticated user
        db: Database session
        
    Raises:
        HTTPException: If old password is incorrect
    """
    # Verify old password
    if not verify_password(password_data.old_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect password",
        )
    
    # Update password
    current_user.hashed_password = get_password_hash(password_data.new_password)
    current_user.updated_at = datetime.utcnow()
    
    await db.commit()
    
    return None


# Telegram OAuth endpoints
@router.get("/telegram")
async def telegram_login_redirect():
    """
    Redirect to Telegram login.
    
    Returns:
        Redirect response to Telegram bot
    """
    telegram_bot_username = settings.telegram_bot_username or "bot"
    
    # Return HTML with Telegram login widget
    return {
        "message": "Use Telegram login widget",
        "bot_username": telegram_bot_username,
        "callback_url": f"{settings.telegram_base_url}/auth/telegram/callback",
    }


def _verify_telegram_auth_data(data: dict) -> bool:
    """
    Verify Telegram login widget data using SHA256 hash.
    
    Args:
        data: Dictionary with auth data from Telegram
        
    Returns:
        True if data is valid, False otherwise
    """
    check_hash = data.pop("hash", None)
    if not check_hash:
        return False
    
    # Create data check string
    data_check_list = []
    for key in sorted(data.keys()):
        data_check_list.append(f"{key}={data[key]}")
    
    data_check_string = "\n".join(data_check_list)
    
    # Verify hash
    secret_key = hashlib.sha256(settings.telegram_bot_token.encode()).digest()
    computed_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256
    ).hexdigest()
    
    return computed_hash == check_hash


@router.api_route("/telegram/callback", methods=["GET", "POST"])
async def telegram_login_callback(
    id: int = Query(...),
    first_name: str = Query(...),
    last_name: str = Query(None),
    username: str = Query(None),
    photo_url: str = Query(None),
    auth_date: int = Query(...),
    hash: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Telegram login callback.
    
    Args:
        id: Telegram user ID
        first_name: User's first name
        last_name: User's last name (optional)
        username: User's Telegram username (optional)
        photo_url: User's profile photo URL (optional)
        auth_date: Authentication date
        hash: Telegram authentication hash
        db: Database session
        
    Returns:
        Redirect to dashboard with tokens
        
    Raises:
        HTTPException: If authentication fails
    """
    # Verify auth data
    auth_data = {
        "id": str(id),
        "first_name": first_name,
        "auth_date": str(auth_date),
    }
    if last_name:
        auth_data["last_name"] = last_name
    if username:
        auth_data["username"] = username
    if photo_url:
        auth_data["photo_url"] = photo_url
    
    auth_data["hash"] = hash
    
    if not _verify_telegram_auth_data(auth_data):
        logger.warning(f"Invalid Telegram auth hash for user {id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Telegram authentication",
        )
    
    # Check if user exists
    result = await db.execute(select(User).where(User.telegram_id == id))
    user = result.scalar_one_or_none()
    
    if user:
        # Update last login
        user.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(user)
    else:
        # Create new user from Telegram data
        # Generate username
        telegram_username = username or f"tg_{id}"
        
        # Check if username exists
        result = await db.execute(
            select(User).where(User.username == telegram_username)
        )
        if result.scalar_one_or_none():
            telegram_username = f"tg_{id}_{datetime.utcnow().timestamp():.0f}"
        
        # Generate email
        telegram_email = f"tg_{id}@telegram.local"
        
        # Check if email exists
        result = await db.execute(
            select(User).where(User.email == telegram_email)
        )
        if result.scalar_one_or_none():
            telegram_email = f"tg_{id}_{datetime.utcnow().timestamp():.0f}@telegram.local"
        
        # Create new user
        full_name = first_name
        if last_name:
            full_name = f"{first_name} {last_name}"
        
        user = User(
            telegram_id=id,
            username=telegram_username,
            email=telegram_email,
            full_name=full_name,
            hashed_password=get_password_hash(f"telegram_{id}_{datetime.utcnow().timestamp()}"),
            is_active=True,
        )
        
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        logger.info(f"New user registered via Telegram: {user.id} (Telegram ID: {id})")
    
    # Generate tokens
    access_token = create_access_token(data={"sub": user.id})
    refresh_token = create_refresh_token(data={"sub": user.id})
    
    # Redirect to dashboard with tokens in query parameters
    dashboard_url = f"{settings.telegram_base_url}/dashboard"
    params = {
        "access_token": access_token,
        "refresh_token": refresh_token,
    }
    redirect_url = f"{dashboard_url}?{urlencode(params)}"
    
    return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)


@router.get("/telegram/link")
async def telegram_link_redirect(current_user: User = Depends(get_current_active_user)):
    """
    Get Telegram linking information for authenticated user.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        Telegram linking information
    """
    if current_user.telegram_id:
        return {
            "status": "already_linked",
            "telegram_id": current_user.telegram_id,
        }
    
    return {
        "status": "not_linked",
        "bot_username": settings.telegram_bot_username or "bot",
        "user_id": current_user.id,
    }


@router.post("/telegram/link")
async def telegram_link_account(
    telegram_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """
    Link Telegram account to existing user.
    
    Args:
        telegram_id: Telegram user ID to link
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Updated user
        
    Raises:
        HTTPException: If Telegram ID already linked to another user
    """
    # Check if Telegram ID already linked to another user
    result = await db.execute(
        select(User).where(
            User.telegram_id == telegram_id,
            User.id != current_user.id
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This Telegram account is already linked to another user",
        )
    
    # Link Telegram ID
    current_user.telegram_id = telegram_id
    current_user.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(current_user)
    
    logger.info(f"User {current_user.id} linked Telegram ID: {telegram_id}")
    
    return current_user


# Email Verification Endpoints

@router.post("/send-verification-email", response_model=MessageResponse)
async def send_verification_email(
    request: EmailVerificationRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Send email verification link.
    
    Args:
        request: Email verification request
        db: Database session
        
    Returns:
        Success message
        
    Raises:
        HTTPException: If email not found
    """
    # Check if user exists
    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()
    
    if not user:
        # Don't reveal if email exists for security
        return MessageResponse(
            message="If the email is registered, verification link has been sent"
        )
    
    # Skip if already verified
    if user.is_verified:
        return MessageResponse(
            message="Email is already verified"
        )
    
    # Create verification token
    verification_token = create_email_verification_token(request.email)
    
    # In a real application, you would send this via email
    # For now, we'll store it and return it for testing
    logger.info(f"Verification token for {request.email}: {verification_token}")
    
    return MessageResponse(
        message="Verification link has been sent to your email (check logs for token in development)"
    )


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(
    request: EmailVerificationConfirm,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Verify email address.
    
    Args:
        request: Email verification confirmation with token
        db: Database session
        
    Returns:
        Success message
        
    Raises:
        HTTPException: If token is invalid
    """
    # Decode token
    email = decode_email_verification_token(request.token)
    
    # Get user by email
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    # Mark as verified
    user.is_verified = True
    user.email_verified_at = datetime.utcnow()
    user.updated_at = datetime.utcnow()
    
    await db.commit()
    
    logger.info(f"User {user.id} verified email: {email}")
    
    return MessageResponse(
        message="Email verified successfully"
    )


# Password Reset Endpoints

@router.post("/request-password-reset", response_model=MessageResponse)
async def request_password_reset(
    request: PasswordResetRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Request password reset link.
    
    Args:
        request: Password reset request with email
        db: Database session
        
    Returns:
        Success message
        
    Raises:
        HTTPException: If email not found
    """
    # Get user by email
    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()
    
    if not user:
        # Don't reveal if email exists for security
        return MessageResponse(
            message="If the email is registered, password reset link has been sent"
        )
    
    # Create reset token
    reset_token = create_password_reset_token(user.id)
    
    # Store token in database
    user.password_reset_token = reset_token
    user.password_reset_expires = datetime.utcnow() + timedelta(hours=1)
    user.updated_at = datetime.utcnow()
    
    await db.commit()
    
    # In a real application, you would send this via email
    logger.info(f"Password reset token for user {user.id}: {reset_token}")
    
    return MessageResponse(
        message="Password reset link has been sent to your email (check logs for token in development)"
    )


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    request: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Reset password with token.
    
    Args:
        request: Password reset confirmation with token and new password
        db: Database session
        
    Returns:
        Success message
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    # Decode token
    user_id = decode_password_reset_token(request.token)
    
    # Get user
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    # Check if token is still valid
    if not user.password_reset_expires or user.password_reset_expires < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password reset token has expired",
        )
    
    # Update password
    user.hashed_password = get_password_hash(request.new_password)
    user.password_reset_token = None
    user.password_reset_expires = None
    user.updated_at = datetime.utcnow()
    
    await db.commit()
    
    logger.info(f"User {user.id} reset password")
    
    return MessageResponse(
        message="Password has been reset successfully"
    )


# User Profile & Usage Endpoints

@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """
    Get current authenticated user profile (alias for /profile).
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        Current user profile
    """
    return current_user


@router.get("/organization")
async def get_current_organization(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get current user's organization.
    
    Args:
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        Organization data
    """
    if not current_user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User has no organization",
        )
    
    result = await db.execute(
        select(Organization).where(Organization.id == current_user.organization_id)
    )
    org = result.scalar_one_or_none()
    
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )
    
    # Count users in organization
    users_result = await db.execute(
        select(User).where(User.organization_id == org.id)
    )
    users_count = len(users_result.scalars().all())
    
    return {
        "id": org.id,
        "name": org.name,
        "slug": org.slug,
        "description": org.description,
        "is_active": org.is_active,
        "max_users": org.max_users,
        "users_count": users_count,
        "created_at": org.created_at,
        "updated_at": org.updated_at,
    }


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Get user profile by ID (public endpoint).
    
    Args:
        user_id: User ID
        db: Database session
        
    Returns:
        User profile
        
    Raises:
        HTTPException: If user not found
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    return user


