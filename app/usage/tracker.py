"""FastAPI middleware for usage tracking."""
from __future__ import annotations

import json
import time
import logging
from typing import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import decode_token, verify_token_type
from app.models.usage import UsageRecord
from app.models.user import User


logger = logging.getLogger(__name__)
EXCLUDE_PATHS = {"/health", "/", "/docs", "/openapi.json"}


class UsageMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.time()
        status_code = 500
        error_message = None
        response = None

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            status_code = 500
            error_message = str(e)
            raise
        finally:
            # Best-effort logging, non-blocking
            path = request.url.path
            if any(path.startswith(p) for p in EXCLUDE_PATHS):
                pass
            else:
                auth = request.headers.get("authorization") or request.headers.get("Authorization")
                user_id = None
                try:
                    if auth and auth.lower().startswith("bearer "):
                        token = auth.split(" ", 1)[1]
                        payload = decode_token(token)
                        verify_token_type(payload, "access")
                        raw_sub = payload.get("sub")
                        try:
                            user_id = int(raw_sub) if raw_sub is not None else None
                        except (TypeError, ValueError):
                            logger.debug(f"Token sub is not int-convertible: {raw_sub}")
                            user_id = None
                except Exception as e:
                    logger.debug(f"Failed to extract user from token: {e}")
                    user_id = None

                if user_id is not None:
                    duration_ms = int((time.time() - start) * 1000)

                    async with AsyncSessionLocal() as db:
                        try:
                            # Verify user exists
                            user = await db.get(User, user_id)
                            if user:
                                record = UsageRecord(
                                    user_id=user.id,
                                    endpoint=path,
                                    method=request.method,
                                    channel="api",
                                    model_name=None,
                                    prompt_tokens=0,
                                    completion_tokens=0,
                                    total_tokens=0,
                                    response_time_ms=duration_ms,
                                    status_code=status_code,
                                    cost=0,
                                    error_message=error_message,
                                    meta=None,
                                )
                                db.add(record)
                                try:
                                    await db.commit()
                                    logger.debug(f"Logged request: {path} from user {user_id}")
                                except Exception as commit_err:
                                    logger.error(f"Failed to commit usage record: {commit_err}")
                                    await db.rollback()
                            else:
                                logger.debug(f"User {user_id} not found in DB")
                        except Exception as db_err:
                            logger.error(f"Database error during logging: {db_err}")

        return response
