"""Web channel API with i18n support."""
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from app.auth.dependencies import get_current_active_user
from app.models.user import User
from app.channels.texts import help_text, profile_text, echo_text
from app.core.config import settings


router = APIRouter(prefix="/web", tags=["Web"])
logger = logging.getLogger(__name__)

# File upload constraints
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp"
}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


class EchoRequest(BaseModel):
	text: str


class UploadResponse(BaseModel):
	"""Response for file upload."""
	success: bool
	file_path: Optional[str] = None
	message: str
	file_size: Optional[int] = None


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


@router.post("/upload-image", response_model=UploadResponse)
async def upload_image(
	file: UploadFile = File(...),
	current_user: User = Depends(get_current_active_user)
):
	"""
	Upload an image file.
	
	Validates file type, size, and saves to media/uploads directory.
	Returns the relative path to use in agent invocation.
	"""
	try:
		# Validate file is present
		if not file.filename:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="No file provided"
			)
		
		# Validate file extension
		file_ext = Path(file.filename).suffix.lower()
		if file_ext not in ALLOWED_EXTENSIONS:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail=f"Invalid file format. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
			)
		
		# Read file content
		content = await file.read()
		file_size = len(content)
		
		# Validate file size
		if file_size > MAX_FILE_SIZE:
			raise HTTPException(
				status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
				detail=f"File too large. Maximum size: {MAX_FILE_SIZE / (1024 * 1024):.0f} MB"
			)
		
		# Validate MIME type
		if file.content_type not in ALLOWED_MIME_TYPES:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail=f"Invalid content type. Allowed: {', '.join(ALLOWED_MIME_TYPES)}"
			)
		
		# Generate unique filename: timestamp_uuid.ext
		timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
		unique_id = str(uuid.uuid4())[:8]
		filename = f"{timestamp}_{unique_id}{file_ext}"
		
		# Ensure upload directory exists
		upload_dir = Path(settings.base_dir) / "media" / "uploads"
		upload_dir.mkdir(parents=True, exist_ok=True)
		
		# Save file
		file_path = upload_dir / filename
		with open(file_path, "wb") as f:
			f.write(content)
		
		# Return relative path from media directory
		relative_path = f"uploads/{filename}"
		
		logger.info(f"User {current_user.id} uploaded image: {relative_path} ({file_size} bytes)")
		
		return UploadResponse(
			success=True,
			file_path=relative_path,
			message="Image uploaded successfully",
			file_size=file_size
		)
	
	except HTTPException:
		raise
	except Exception as e:
		logger.error(f"Error uploading image: {e}")
		raise HTTPException(
			status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
			detail="Failed to upload image"
		)
	finally:
		await file.close()

