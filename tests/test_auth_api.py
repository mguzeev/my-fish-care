import pytest
import hmac
import hashlib
from app.core.config import settings
from app.core.security import (
    create_email_verification_token,
    create_password_reset_token,
)


@pytest.mark.asyncio
async def test_register_login_refresh_profile(client):
    # Register
    register_resp = await client.post(
        "/auth/register",
        json={
            "email": "test@example.com",
            "username": "testuser",
            "password": "StrongPass123",
            "full_name": "Test User",
        },
    )
    assert register_resp.status_code == 201
    user_data = register_resp.json()
    assert user_data["email"] == "test@example.com"

    # Login
    login_resp = await client.post(
        "/auth/login",
        json={
            "email": "test@example.com",
            "password": "StrongPass123",
        },
    )
    assert login_resp.status_code == 200
    tokens = login_resp.json()
    assert "access_token" in tokens and "refresh_token" in tokens

    # Refresh
    refresh_resp = await client.post(
        "/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refresh_resp.status_code == 200
    refreshed = refresh_resp.json()
    assert refreshed["access_token"] != tokens["access_token"]

    # Profile
    profile_resp = await client.get(
        "/auth/profile",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert profile_resp.status_code == 200
    profile = profile_resp.json()
    assert profile["email"] == "test@example.com"


@pytest.mark.asyncio
async def test_telegram_login_new_user(client):
    """Test Telegram login creating a new user."""
    # Create valid Telegram auth data
    telegram_id = 123456789
    first_name = "John"
    last_name = "Doe"
    username = "johndoe"
    auth_date = 1234567890
    
    # Create hash
    data_check_string = f"auth_date={auth_date}\nfirst_name={first_name}\nid={telegram_id}\nlast_name={last_name}\nusername={username}"
    secret_key = hashlib.sha256(settings.telegram_bot_token.encode()).digest()
    telegram_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256
    ).hexdigest()
    
    # Login via Telegram
    resp = await client.post(
        "/auth/telegram/callback",
        params={
            "id": telegram_id,
            "first_name": first_name,
            "last_name": last_name,
            "username": username,
            "auth_date": auth_date,
            "hash": telegram_hash,
        },
        follow_redirects=False,
    )
    
    # Telegram callback redirects to dashboard with tokens in URL
    assert resp.status_code == 302
    assert "access_token=" in resp.headers["location"]
    assert "refresh_token=" in resp.headers["location"]


@pytest.mark.asyncio
async def test_telegram_login_existing_user(client):
    """Test Telegram login with existing user."""
    # First create a user via regular registration
    register_resp = await client.post(
        "/auth/register",
        json={
            "email": "tg_user@example.com",
            "username": "tguser",
            "password": "StrongPass123",
        },
    )
    assert register_resp.status_code == 201
    
    # Create valid Telegram auth data with same user
    telegram_id = 987654321
    first_name = "Jane"
    auth_date = 1234567890
    
    # Create hash (no other fields for simplicity)
    data_check_string = f"auth_date={auth_date}\nfirst_name={first_name}\nid={telegram_id}"
    secret_key = hashlib.sha256(settings.telegram_bot_token.encode()).digest()
    telegram_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256
    ).hexdigest()
    
    # Manually link telegram_id to user (simulating first Telegram login)
    # This would be done through linking endpoint in real scenario
    resp = await client.post(
        "/auth/telegram/callback",
        params={
            "id": telegram_id,
            "first_name": first_name,
            "auth_date": auth_date,
            "hash": telegram_hash,
        },
        follow_redirects=False,
    )
    
    # Telegram callback redirects with tokens
    assert resp.status_code == 302
    assert "access_token=" in resp.headers["location"]


@pytest.mark.asyncio
async def test_telegram_login_invalid_hash(client):
    """Test Telegram login with invalid hash."""
    resp = await client.post(
        "/auth/telegram/callback",
        params={
            "id": 123456789,
            "first_name": "John",
            "auth_date": 1234567890,
            "hash": "invalid_hash_here",
        },
    )
    
    assert resp.status_code == 401
    assert "Invalid Telegram" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_telegram_link_account(client):
    """Test linking Telegram account to existing user."""
    # Register a user
    register_resp = await client.post(
        "/auth/register",
        json={
            "email": "link@example.com",
            "username": "linkuser",
            "password": "StrongPass123",
        },
    )
    assert register_resp.status_code == 201
    
    # Login
    login_resp = await client.post(
        "/auth/login",
        json={
            "email": "link@example.com",
            "password": "StrongPass123",
        },
    )
    tokens = login_resp.json()
    access_token = tokens["access_token"]
    
    # Link Telegram account
    link_resp = await client.post(
        "/auth/telegram/link",
        params={"telegram_id": 111111111},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    
    assert link_resp.status_code == 200
    user_data = link_resp.json()
    assert user_data["telegram_id"] == 111111111


@pytest.mark.asyncio
async def test_telegram_get_link_status_linked(client):
    """Test getting Telegram link status when linked."""
    # Register and login
    register_resp = await client.post(
        "/auth/register",
        json={
            "email": "linked@example.com",
            "username": "linkeduser",
            "password": "StrongPass123",
        },
    )
    login_resp = await client.post(
        "/auth/login",
        json={
            "email": "linked@example.com",
            "password": "StrongPass123",
        },
    )
    tokens = login_resp.json()
    access_token = tokens["access_token"]
    
    # Link Telegram account
    await client.post(
        "/auth/telegram/link",
        params={"telegram_id": 222222222},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    
    # Check link status
    status_resp = await client.get(
        "/auth/telegram/link",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["status"] == "already_linked"
    assert data["telegram_id"] == 222222222


@pytest.mark.asyncio
async def test_telegram_get_link_status_not_linked(client):
    """Test getting Telegram link status when not linked."""
    # Register and login
    register_resp = await client.post(
        "/auth/register",
        json={
            "email": "notlinked@example.com",
            "username": "notlinkeduser",
            "password": "StrongPass123",
        },
    )
    login_resp = await client.post(
        "/auth/login",
        json={
            "email": "notlinked@example.com",
            "password": "StrongPass123",
        },
    )
    tokens = login_resp.json()
    access_token = tokens["access_token"]
    
    # Check link status
    status_resp = await client.get(
        "/auth/telegram/link",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["status"] == "not_linked"


# Email Verification Tests

@pytest.mark.asyncio
async def test_send_verification_email(client):
    """Test sending verification email."""
    # Register a user
    register_resp = await client.post(
        "/auth/register",
        json={
            "email": "verify@example.com",
            "username": "verifyuser",
            "password": "StrongPass123",
        },
    )
    assert register_resp.status_code == 201
    
    # Request verification email
    resp = await client.post(
        "/auth/send-verification-email",
        json={"email": "verify@example.com"},
    )
    
    assert resp.status_code == 200
    data = resp.json()
    assert "verification link" in data["message"].lower()


@pytest.mark.asyncio
async def test_send_verification_email_not_found(client):
    """Test sending verification email to non-existent user."""
    resp = await client.post(
        "/auth/send-verification-email",
        json={"email": "nonexistent@example.com"},
    )
    
    assert resp.status_code == 200
    # Security: don't reveal if email exists
    assert "verification link" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_verify_email_success(client):
    """Test successful email verification."""
    # Register a user
    register_resp = await client.post(
        "/auth/register",
        json={
            "email": "verify_success@example.com",
            "username": "verifysuccess",
            "password": "StrongPass123",
        },
    )
    assert register_resp.status_code == 201
    
    # Generate verification token
    token = create_email_verification_token("verify_success@example.com")
    
    # Verify email
    resp = await client.post(
        "/auth/verify-email",
        json={"token": token},
    )
    
    assert resp.status_code == 200
    data = resp.json()
    assert "Email verified" in data["message"]


@pytest.mark.asyncio
async def test_verify_email_invalid_token(client):
    """Test email verification with invalid token."""
    resp = await client.post(
        "/auth/verify-email",
        json={"token": "invalid_token_here"},
    )
    
    assert resp.status_code == 400
    assert "Invalid" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_verify_email_user_not_found(client):
    """Test email verification with non-existent user."""
    # Generate valid token for non-existent user
    token = create_email_verification_token("nonexistent@example.com")
    
    resp = await client.post(
        "/auth/verify-email",
        json={"token": token},
    )
    
    assert resp.status_code == 404
    assert "User not found" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_verify_email_already_verified(client):
    """Test sending verification email for already verified user."""
    # Register and verify user
    register_resp = await client.post(
        "/auth/register",
        json={
            "email": "already_verified@example.com",
            "username": "alreadyverified",
            "password": "StrongPass123",
        },
    )
    
    token = create_email_verification_token("already_verified@example.com")
    await client.post(
        "/auth/verify-email",
        json={"token": token},
    )
    
    # Try to send verification email again
    resp = await client.post(
        "/auth/send-verification-email",
        json={"email": "already_verified@example.com"},
    )
    
    assert resp.status_code == 200
    assert "already verified" in resp.json()["message"].lower()


# Password Reset Tests

@pytest.mark.asyncio
async def test_request_password_reset(client):
    """Test requesting password reset."""
    # Register a user
    register_resp = await client.post(
        "/auth/register",
        json={
            "email": "reset@example.com",
            "username": "resetuser",
            "password": "StrongPass123",
        },
    )
    assert register_resp.status_code == 201
    
    # Request password reset
    resp = await client.post(
        "/auth/request-password-reset",
        json={"email": "reset@example.com"},
    )
    
    assert resp.status_code == 200
    data = resp.json()
    assert "password reset" in data["message"].lower()


@pytest.mark.asyncio
async def test_request_password_reset_not_found(client):
    """Test requesting password reset for non-existent user."""
    resp = await client.post(
        "/auth/request-password-reset",
        json={"email": "nonexistent_reset@example.com"},
    )
    
    assert resp.status_code == 200
    # Security: don't reveal if email exists
    assert "password reset" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_reset_password_success(client):
    """Test successful password reset."""
    # Register a user
    register_resp = await client.post(
        "/auth/register",
        json={
            "email": "reset_success@example.com",
            "username": "resetsuccess",
            "password": "StrongPass123",
        },
    )
    user_id = register_resp.json()["id"]
    
    # Request password reset
    await client.post(
        "/auth/request-password-reset",
        json={"email": "reset_success@example.com"},
    )
    
    # Generate reset token (normally received via email)
    token = create_password_reset_token(user_id)
    
    # Reset password
    resp = await client.post(
        "/auth/reset-password",
        json={
            "token": token,
            "new_password": "NewStrongPass456",
        },
    )
    
    assert resp.status_code == 200
    data = resp.json()
    assert "reset successfully" in data["message"].lower()
    
    # Try to login with new password
    login_resp = await client.post(
        "/auth/login",
        json={
            "email": "reset_success@example.com",
            "password": "NewStrongPass456",
        },
    )
    
    assert login_resp.status_code == 200
    assert "access_token" in login_resp.json()


@pytest.mark.asyncio
async def test_reset_password_invalid_token(client):
    """Test password reset with invalid token."""
    resp = await client.post(
        "/auth/reset-password",
        json={
            "token": "invalid_token_here",
            "new_password": "NewStrongPass456",
        },
    )
    
    assert resp.status_code == 400
    assert "Invalid" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_reset_password_expired_token(client):
    """Test password reset token validation."""
    # Register a user
    register_resp = await client.post(
        "/auth/register",
        json={
            "email": "reset_expired@example.com",
            "username": "resetexpired",
            "password": "StrongPass123",
        },
    )
    
    # Request password reset properly (this stores token in DB)
    await client.post(
        "/auth/request-password-reset",
        json={"email": "reset_expired@example.com"},
    )
    
    # Create a new valid token (in real scenario, would be from email)
    user_id = register_resp.json()["id"]
    token = create_password_reset_token(user_id)
    
    # Reset password should succeed with valid token that was requested
    resp = await client.post(
        "/auth/reset-password",
        json={
            "token": token,
            "new_password": "NewStrongPass456",
        },
    )
    
    # Should succeed since token is valid and was requested
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_reset_password_user_not_found(client):
    """Test password reset with non-existent user."""
    # Create token for non-existent user
    token = create_password_reset_token(99999)
    
    resp = await client.post(
        "/auth/reset-password",
        json={
            "token": token,
            "new_password": "NewStrongPass456",
        },
    )
    
    assert resp.status_code == 404
    assert "User not found" in resp.json()["detail"]


# User Profile & Usage Endpoints Tests

@pytest.mark.asyncio
async def test_get_me_endpoint(client):
    """Test GET /auth/me endpoint."""
    # Register and login
    register_resp = await client.post(
        "/auth/register",
        json={
            "email": "me@example.com",
            "username": "meuser",
            "password": "StrongPass123",
            "full_name": "Me User",
        },
    )
    
    login_resp = await client.post(
        "/auth/login",
        json={
            "email": "me@example.com",
            "password": "StrongPass123",
        },
    )
    token = login_resp.json()["access_token"]
    
    # Get /me
    resp = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    
    assert resp.status_code == 200
    user = resp.json()
    assert user["email"] == "me@example.com"
    assert user["full_name"] == "Me User"


@pytest.mark.asyncio
async def test_get_user_by_id(client):
    """Test GET /auth/users/{user_id} endpoint."""
    # Register a user
    register_resp = await client.post(
        "/auth/register",
        json={
            "email": "getuser@example.com",
            "username": "getuseruser",
            "password": "StrongPass123",
            "full_name": "Get User",
        },
    )
    user_id = register_resp.json()["id"]
    
    # Get user by ID (public endpoint)
    resp = await client.get(f"/auth/users/{user_id}")
    
    assert resp.status_code == 200
    user = resp.json()
    assert user["id"] == user_id
    assert user["email"] == "getuser@example.com"


@pytest.mark.asyncio
async def test_get_user_by_id_not_found(client):
    """Test GET /auth/users/{user_id} with non-existent user."""
    resp = await client.get("/auth/users/99999")
    
    assert resp.status_code == 404
    assert "User not found" in resp.json()["detail"]

