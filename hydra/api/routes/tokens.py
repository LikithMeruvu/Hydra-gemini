"""Admin token management routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/admin", tags=["tokens"])


class CreateTokenRequest(BaseModel):
    name: str = ""


@router.post("/tokens/create")
async def create_token(req: CreateTokenRequest):
    """Generate a new API access token."""
    from hydra.api.app import token_service

    if not token_service:
        raise HTTPException(503, "Gateway not initialized")

    result = await token_service.create_token(req.name)
    return {
        "status": "created",
        "token": result["token"],  # Only shown ONCE at creation
        "id": result["id"],
        "name": result["name"],
        "warning": "Save this token now — it won't be shown again!",
    }


@router.get("/tokens/list")
async def list_tokens():
    """List all tokens with usage stats (tokens themselves are hidden)."""
    from hydra.api.app import token_service

    if not token_service:
        raise HTTPException(503, "Gateway not initialized")

    tokens = await token_service.list_tokens()
    return {"total": len(tokens), "tokens": tokens}


@router.delete("/tokens/{token_id}")
async def delete_token(token_id: str):
    """Revoke an API token."""
    from hydra.api.app import token_service

    if not token_service:
        raise HTTPException(503, "Gateway not initialized")

    removed = await token_service.delete_token(token_id)
    if not removed:
        raise HTTPException(404, "Token not found")
    return {"status": "deleted", "id": token_id}
