"""FastAPI middleware for usage tracking."""
from __future__ import annotations

import json
import time
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
            return response
        except Exception as e:
            status_code = 500
            error_message = str(e)
            raise
        finally:
            # Best-effort logging, non-blocking
            path = request.url.path
            if any(path.startswith(p) for p in EXCLUDE_PATHS):
                return

            auth = request.headers.get("authorization") or request.headers.get("Authorization")
            user_id = None
            try:
                if auth and auth.lower().startswith("bearer "):
                    token = auth.split(" ", 1)[1]
                    payload = decode_token(token)
                    verify_token_type(payload, "access")
                    user_id = payload.get("sub")
            except Exception:
                user_id = None

            if user_id is None:
                return

            duration_ms = int((time.time() - start) * 1000)

            async with AsyncSessionLocal() as db:
                # Verify user exists
                user = await db.get(User, user_id)
                if not user:
                    return

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
                except Exception:
                    await db.rollback()
                    # swallow errors to not impact response
                    return
