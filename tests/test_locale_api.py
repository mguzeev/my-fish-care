import pytest


@pytest.mark.asyncio
async def test_change_locale(client):
    # Register and login
    register_resp = await client.post(
        "/auth/register",
        json={
            "email": "loc@example.com",
            "username": "loc_user",
            "password": "Local3Pass",
        },
    )
    assert register_resp.status_code == 201

    login_resp = await client.post(
        "/auth/login",
        json={"email": "loc@example.com", "password": "Local3Pass"},
    )
    assert login_resp.status_code == 200
    tokens = login_resp.json()

    # Change locale to 'uk'
    change_resp = await client.put(
        "/auth/locale",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"locale": "uk"},
    )
    assert change_resp.status_code == 200
    assert change_resp.json()["locale"] == "uk"

    # Update profile via PUT /auth/profile also supports locale
    profile_resp = await client.put(
        "/auth/profile",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"locale": "ru"},
    )
    assert profile_resp.status_code == 200
    assert profile_resp.json()["locale"] == "ru"
