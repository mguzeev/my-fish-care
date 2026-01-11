import pytest


@pytest.mark.asyncio
async def test_web_help_profile_echo_localized(client):
    # Register and login
    register_resp = await client.post(
        "/auth/register",
        json={
            "email": "web@example.com",
            "username": "web_user",
            "password": "WebPass123",
        },
    )
    assert register_resp.status_code == 201

    login_resp = await client.post(
        "/auth/login",
        json={"email": "web@example.com", "password": "WebPass123"},
    )
    tokens = login_resp.json()

    # Set locale to Ukrainian
    change_resp = await client.put(
        "/auth/locale",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"locale": "uk"},
    )
    assert change_resp.status_code == 200

    # Help is localized
    help_resp = await client.get(
        "/web/help",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert help_resp.status_code == 200
    assert "Доступні команди" in help_resp.json()["text"]

    # Profile is localized
    profile_resp = await client.get(
        "/web/profile",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert profile_resp.status_code == 200
    assert "Ваш профіль" in profile_resp.json()["text"]

    # Echo is localized
    echo_resp = await client.post(
        "/web/echo",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"text": "Привіт"},
    )
    assert echo_resp.status_code == 200
    assert "Ви написали" in echo_resp.json()["text"]
