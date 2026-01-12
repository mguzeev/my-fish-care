import os
import asyncio
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool

# Ensure required env vars exist before app imports settings
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

from app.core.database import Base, get_db, AsyncSessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.core.security import get_password_hash, create_access_token  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.agent import Agent  # noqa: E402
from app.models.llm_model import LLMModel  # noqa: E402


TEST_DATABASE_URL = os.environ["DATABASE_URL"]


# Async SQLite engine with shared memory for all sessions
engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

# Session factory bound to the test engine
TestingSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
async def setup_database():
    """Create database schema once for the test session."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest.fixture(autouse=True)
async def clean_database():
    """Clear all tables before each test for isolation."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest.fixture()
async def db_session(setup_database):
    """Yield a database session and roll back after test."""
    async with TestingSessionLocal() as session:
        try:
            yield session
        finally:
            await session.rollback()


@pytest.fixture()
async def client(monkeypatch, setup_database):
    """FastAPI test client with DB dependency overridden."""

    async def override_get_db():
        async with TestingSessionLocal() as session:
            try:
                yield session
            finally:
                await session.rollback()

    app.dependency_overrides[get_db] = override_get_db
    # Ensure other modules using AsyncSessionLocal pick up the test session maker
    monkeypatch.setattr("app.core.database.AsyncSessionLocal", TestingSessionLocal)

    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture()
async def user_factory(db_session):
    """Factory to create users in the test DB."""

    async def _create_user(
        email: str = "user@example.com",
        username: str = "user",
        password: str = "secret123",
        **kwargs,
    ) -> User:
        user = User(
            email=email,
            username=username,
            hashed_password=get_password_hash(password),
            **kwargs,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    return _create_user


@pytest.fixture()
async def llm_model(db_session):
    """Create default LLM model for tests."""
    model = LLMModel(
        name="gpt-4",
        display_name="GPT-4 (OpenAI)",
        provider="openai",
        api_key="test-key",
        is_default=True,
    )
    db_session.add(model)
    await db_session.commit()
    await db_session.refresh(model)
    return model


@pytest.fixture()
async def agent_factory(db_session, llm_model):
    """Factory to create agents in the test DB."""

    async def _create_agent(
        name: str = "Test Agent",
        slug: str = "test-agent",
        system_prompt: str = "You are a test agent",
        prompt_template: str | None = None,
        model_name: str = "gpt-4",
        llm_model_id: int | None = None,
    ) -> Agent:
        agent = Agent(
            name=name,
            slug=slug,
            system_prompt=system_prompt,
            prompt_template=prompt_template,
            model_name=model_name,
            llm_model_id=llm_model_id or llm_model.id,
        )
        db_session.add(agent)
        await db_session.commit()
        await db_session.refresh(agent)
        return agent

    return _create_agent


@pytest.fixture()
async def user(user_factory, db_session):
    """Create a default test user with organization."""
    from app.models.organization import Organization
    
    # Create org first
    org = Organization(name="Test Org", slug="test-org")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    
    # Create user with organization
    return await user_factory(organization_id=org.id)


@pytest.fixture()
async def auth_header(user):
    """Create Authorization header for the test user."""
    token = create_access_token({"sub": user.id})
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture()
async def admin_client(db_session, client: AsyncClient):
    """Create admin user and return client with admin auth header."""
    admin_user = User(
        email="admin@example.com",
        username="admin",
        hashed_password=get_password_hash("admin123"),
        is_superuser=True,
        organization_id=None,
    )
    db_session.add(admin_user)
    await db_session.commit()
    await db_session.refresh(admin_user)
    
    token = create_access_token({"sub": admin_user.id})
    
    # Create a new client with admin headers
    async with AsyncClient(app=app, base_url="http://test", headers={"Authorization": f"Bearer {token}"}) as ac:
        yield ac