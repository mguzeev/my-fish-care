"""Web channel API with i18n support."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.auth.dependencies import get_current_active_user
from app.models.user import User
from app.channels.texts import help_text, profile_text, echo_text


router = APIRouter(prefix="/web", tags=["Web"])


class EchoRequest(BaseModel):
	text: str


@router.get("/help")
async def web_help(current_user: User = Depends(get_current_active_user)):
	return {"text": help_text(current_user.locale)}


@router.get("/profile")
async def web_profile(current_user: User = Depends(get_current_active_user)):
	text = profile_text(
		name=current_user.full_name,
		username=current_user.username,
		email=current_user.email,
		role=current_user.role,
		is_active=current_user.is_active,
		is_verified=current_user.is_verified,
		locale=current_user.locale,
	)
	return {"text": text}


@router.post("/echo")
async def web_echo(payload: EchoRequest, current_user: User = Depends(get_current_active_user)):
	return {"text": echo_text(payload.text, current_user.locale)}

