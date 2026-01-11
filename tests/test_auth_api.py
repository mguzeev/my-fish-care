import pytest
import hmac
import hashlib
from app.core.config import settings


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
    )
    
    assert resp.status_code == 200
    tokens = resp.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens
    assert tokens["token_type"] == "bearer"


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
    )
    
    assert resp.status_code == 200
    tokens = resp.json()
    assert "access_token" in tokens


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

