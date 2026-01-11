import pytest
from datetime import datetime, timedelta
from app.models.user import User
from app.models.session import Session


@pytest.mark.asyncio
async def test_user_defaults(db_session):
    user = User(
        email="alice@example.com",
        username="alice",
        hashed_password="hashed",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    assert user.is_active is True
    assert user.is_verified is False
    assert user.role == "user"
    assert isinstance(user.created_at, datetime)


@pytest.mark.asyncio
async def test_session_links_user(db_session, user_factory):
    user = await user_factory(email="bob@example.com", username="bob")
    session = Session(
        user_id=user.id,
        session_id="sess-1",
        channel="telegram",
        context=None,
        expires_at=datetime.utcnow() + timedelta(hours=1),
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)

    assert session.user_id == user.id
    assert session.channel == "telegram"
    # Relationship should resolve to the same user
    assert session.user.email == user.email
