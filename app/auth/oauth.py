"""OAuth authentication service."""
import logging
from typing import Optional, Dict, Any
from authlib.integrations.starlette_client import OAuth, OAuthError
from starlette.config import Config
from fastapi import HTTPException, status
from app.core.config import settings

logger = logging.getLogger(__name__)

# Initialize OAuth with Starlette config
config = Config(environ={
    "GOOGLE_CLIENT_ID": settings.google_client_id or "",
    "GOOGLE_CLIENT_SECRET": settings.google_client_secret or "",
})

oauth = OAuth(config)

# Register Google OAuth
oauth.register(
    name='google',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)


async def get_google_oauth_url(redirect_uri: str) -> str:
    """
    Generate Google OAuth authorization URL.
    
    Args:
        redirect_uri: The callback URL after OAuth authorization
        
    Returns:
        Authorization URL
    """
    try:
        redirect_url = await oauth.google.create_authorization_url(
            redirect_uri,
            prompt='select_account'
        )
        return redirect_url['url']
    except Exception as e:
        logger.error(f"Error creating Google OAuth URL: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create OAuth authorization URL"
        )


async def get_google_user_info(token: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get user information from Google using access token.
    
    Args:
        token: OAuth token dictionary
        
    Returns:
        User information from Google
        
    Raises:
        HTTPException: If unable to fetch user info
    """
    try:
        resp = await oauth.google.get('https://www.googleapis.com/oauth2/v3/userinfo', token=token)
        user_info = resp.json()
        return user_info
    except Exception as e:
        logger.error(f"Error fetching Google user info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch user information from Google"
        )


def validate_oauth_config() -> None:
    """
    Validate that OAuth configuration is properly set.
    
    Raises:
        RuntimeError: If OAuth credentials are missing
    """
    if not settings.google_client_id or not settings.google_client_secret:
        logger.warning("Google OAuth credentials not configured")
        raise RuntimeError(
            "Google OAuth is not configured. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET"
        )
    logger.info("Google OAuth configuration validated")
