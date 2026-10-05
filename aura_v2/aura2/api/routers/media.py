"""
Receives a photo the user already captured (browser-consented, via
st.camera_input in the UI). This endpoint never triggers capture itself —
by the time a request reaches here, the user has already pressed the
button in their own browser. Saved to local disk for the demo; swap
`_PHOTO_DIR` for real object storage (S3/GCS) before any real deployment.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile

from api.deps import get_current_user_id
from database.connection import get_connection
from utils.logging import get_logger

router = APIRouter(prefix="/media", tags=["media"])
log = get_logger("api.media")

_PHOTO_DIR = Path("/tmp/aura_photos")


@router.post("/save-photo")
async def save_photo(photo: UploadFile = File(...), user_id: str = Depends(get_current_user_id)) -> dict:
    _PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    photo_id = str(uuid.uuid4())
    ext = Path(photo.filename or "photo.jpg").suffix or ".jpg"
    out_path = _PHOTO_DIR / f"{user_id}_{photo_id}{ext}"
    out_path.write_bytes(await photo.read())

    async with get_connection() as conn:
        await conn.execute(
            """INSERT INTO audit_events (user_id, action, tool_name, success, detail)
               VALUES (%(uid)s, 'photo_saved', 'camera_capture', true, %(path)s)""",
            {"uid": user_id, "path": str(out_path)},
        )

    log.info("media.photo_saved", extra={"user_id": user_id, "photo_id": photo_id})
    return {"photo_id": photo_id, "saved": True}
