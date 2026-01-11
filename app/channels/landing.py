"""Landing page and static page routes."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
import os

from app.i18n.translations import get_translations, translate
from app.core.config import settings

router = APIRouter(tags=["landing"])

# Setup Jinja2 for template rendering
template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
env = Environment(loader=FileSystemLoader(template_dir))


def _render_template(template_name: str, language: str = "en", **context):
    """Render a Jinja2 template with translations."""
    template = env.get_template(template_name)
    translations = get_translations(language)
    
    def t(key: str) -> str:
        return translations.get(key, key)
    
    return template.render(
        language=language,
        t=t,
        translations=translations,
        **context
    )


@router.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    """Serve the landing page with language support."""
    language = request.query_params.get("lang", "en")
    
    # Validate language
    if language not in ["en", "ru", "uk"]:
        language = "en"
    
    html = _render_template(
        "landing.html", 
        language=language,
        bot_username=settings.telegram_bot_username or "bot",
        telegram_base_url=settings.telegram_base_url
    )
    response = HTMLResponse(html)
    response.headers["Cache-Control"] = "public, max-age=300"
    return response


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Serve the login page."""
    language = request.query_params.get("lang", "en")
    
    if language not in ["en", "ru", "uk"]:
        language = "en"
    
    html = _render_template(
        "login.html", 
        language=language,
        bot_username=settings.telegram_bot_username or "bot",
        telegram_base_url=settings.telegram_base_url
    )
    return html


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Serve the registration page."""
    language = request.query_params.get("lang", "en")
    
    if language not in ["en", "ru", "uk"]:
        language = "en"
    
    html = _render_template(
        "register.html", 
        language=language,
        bot_username=settings.telegram_bot_username or "bot",
        telegram_base_url=settings.telegram_base_url
    )
    return html


@router.get("/about", response_class=HTMLResponse)
async def about_page(request: Request):
    """Serve the about page."""
    language = request.query_params.get("lang", "en")
    
    if language not in ["en", "ru", "uk"]:
        language = "en"
    
    html = _render_template("about.html", language=language)
    return html


@router.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request):
    """Serve the privacy policy page."""
    language = request.query_params.get("lang", "en")
    
    if language not in ["en", "ru", "uk"]:
        language = "en"
    
    html = _render_template("privacy.html", language=language)
    return html


@router.get("/terms", response_class=HTMLResponse)
async def terms_page(request: Request):
    """Serve the terms of service page."""
    language = request.query_params.get("lang", "en")
    
    if language not in ["en", "ru", "uk"]:
        language = "en"
    
    html = _render_template("terms.html", language=language)
    return html


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """Serve the user dashboard page."""
    language = request.query_params.get("lang", "en")
    
    if language not in ["en", "ru", "uk"]:
        language = "en"
    
    html = _render_template(
        "dashboard.html",
        language=language,
        bot_username=settings.telegram_bot_username or "bot",
        telegram_base_url=settings.telegram_base_url or "http://localhost:8000"
    )
    return html


@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    """Serve the admin panel page."""
    language = request.query_params.get("lang", "en")
    
    if language not in ["en", "ru", "uk"]:
        language = "en"
    
    html = _render_template(
        "admin.html",
        language=language
    )
    return html


@router.get("/status", response_class=HTMLResponse)
async def status_page():
    """Serve the system status page."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Status</title>
        <link rel="stylesheet" href="/static/css/style.css">
    </head>
    <body style="padding: 2rem;">
        <h1>System Status</h1>
        <p style="color: #10b981; font-size: 1.2rem;">✅ All systems operational</p>
        <p>API: <strong>Operational</strong></p>
        <p>Database: <strong>Operational</strong></p>
        <p>Webhooks: <strong>Operational</strong></p>
        <p><a href="/" style="color: #1e40af; text-decoration: none;">← Back to Home</a></p>
    </body>
    </html>
    """
