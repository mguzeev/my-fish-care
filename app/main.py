# Follow SYSTEM_OVERVIEW.md and ARCHITECTURE_AND_COMPONENTS.md
"""FastAPI application entry point."""
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from typing import Optional
from pathlib import Path
from app.core.config import settings, validate_paddle_settings
from app.core.database import init_db, close_db
from app.auth.router import router as auth_router
from app.agents.router import router as agents_router
from app.channels.telegram import telegram_channel
from app.channels.web import router as web_router
from app.channels.landing import router as landing_router
from app.billing.router import router as billing_router
from app.admin.router import router as admin_router
from app.analytics.router import router as analytics_router
from app.webhooks.router import router as webhooks_router
from app.usage.tracker import UsageMiddleware


# Configure logging
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting application...")
    validate_paddle_settings(settings)
    await init_db()
    
    # Start Telegram bot
    if settings.telegram_bot_token:
        asyncio.create_task(telegram_channel.start())
    
    yield
    
    # Shutdown
    logger.info("Shutting down application...")
    if telegram_channel.is_running:
        await telegram_channel.stop()
    await close_db()


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)

# Add Session Middleware (required for OAuth)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="bot_session",
    max_age=3600,  # 1 hour
    same_site="lax",
    https_only=not settings.debug,  # Use secure cookies in production
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)

# Cache control middleware for static files
@app.middleware("http")
async def add_cache_control(request: Request, call_next):
    """Add cache control headers for static files."""
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response

# Include routers
app.include_router(landing_router)
app.include_router(auth_router)
app.include_router(agents_router)
app.include_router(web_router)
app.include_router(billing_router)
app.include_router(admin_router)
app.include_router(analytics_router)
app.include_router(webhooks_router)

# Mount static files
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Usage tracking middleware (non-blocking, low priority)
# Note: Always enabled to track API usage regardless of debug mode
# Usage logging is essential for billing and analytics
app.add_middleware(UsageMiddleware)

@app.post(settings.telegram_webhook_path)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: Optional[str] = Header(None),
):
    """
    Telegram webhook endpoint.
    
    Args:
        request: FastAPI request
        x_telegram_bot_api_secret_token: Telegram secret token header
        
    Returns:
        Success response
        
    Raises:
        HTTPException: If webhook secret is invalid
    """
    # Verify webhook secret
    if settings.telegram_webhook_secret:
        if x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
            logger.warning("Invalid webhook secret token")
            raise HTTPException(status_code=403, detail="Invalid secret token")
    
    # Get update data
    update_data = await request.json()
    
    # Process update
    await telegram_channel.handle_message(update_data)
    
    return {"ok": True}




@app.get("/")
async def root(request: Request):
    """Root endpoint - redirect to landing page."""
    # If accessing from browser, show landing page
    user_agent = request.headers.get("user-agent", "").lower()
    if "mozilla" in user_agent or "chrome" in user_agent or "safari" in user_agent:
        # Render landing page for browser requests
        from app.channels.landing import _render_template
        html = _render_template("landing.html", language="en")
        from fastapi.responses import HTMLResponse
        return HTMLResponse(content=html)
    
    # For API requests, return JSON
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "telegram_bot": telegram_channel.get_status(),
        "mode": "webhook" if settings.telegram_use_webhook else "polling",
    }


