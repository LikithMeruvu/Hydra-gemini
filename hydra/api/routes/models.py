"""GET /v1/models — OpenAI-compatible model listing."""

from __future__ import annotations

from fastapi import APIRouter

from hydra.core.constants import ALL_MODELS

router = APIRouter(tags=["models"])


@router.get("/v1/models")
async def list_models():
    """Return available models in OpenAI format.

    This endpoint is what IDEs (Cursor, Continue, Cline) call to
    populate their model dropdown.
    """
    models = []
    for model_id in ALL_MODELS:
        models.append({
            "id": model_id,
            "object": "model",
            "created": 1700000000,
            "owned_by": "google",
            "permission": [],
            "root": model_id,
            "parent": None,
        })
    return {
        "object": "list",
        "data": models,
    }
