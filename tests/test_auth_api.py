import pytest


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
