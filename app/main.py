# Follow SYSTEM_OVERVIEW.md and ARCHITECTURE_AND_COMPONENTS.md
"""FastAPI application entry point."""
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from app.core.config import settings
from app.core.database import init_db, close_db
from app.auth.router import router as auth_router
from app.agents.router import router as agents_router
from app.channels.telegram import telegram_channel
from app.channels.web import router as web_router
from app.billing.router import router as billing_router
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

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)

# Include routers
app.include_router(auth_router)
app.include_router(agents_router)
app.include_router(web_router)
app.include_router(billing_router)

# Usage tracking middleware (non-blocking, low priority)
if not settings.debug:
    # Only add in production to avoid test issues
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
async def root():
    """Root endpoint."""
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


