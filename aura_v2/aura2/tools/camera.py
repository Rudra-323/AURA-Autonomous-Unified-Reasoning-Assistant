"""
Camera tool. A backend tool cannot access a device's camera — that would
mean silent hardware access, which no legitimate app does and no agent
should ever pretend to do. This tool's only job is to signal the UI to show
a capture widget; the browser's own permission prompt handles consent, and
the UI posts the resulting image to POST /media/save-photo (see
api/routers/media.py) once the user actually takes it.
"""

from __future__ import annotations

from langchain_core.tools import tool

from utils.media_markers import REQUEST_CAMERA, build_marker


@tool
def camera_capture(reason: str = "") -> str:
    """Ask the user to take a photo via their device camera. This always
    requires the user to grant camera access in their browser and press
    capture themselves — it cannot happen silently. Use this only when the
    user explicitly asks to take/save a photo.

    Args:
        reason: Brief context for why a photo is being requested, shown to the user.
    """
    label = reason or "Take a photo"
    # Structured marker the API layer turns into a `request_camera` event.
    marker = build_marker(REQUEST_CAMERA, {"label": label})
    return f"{marker}\nI've opened the camera for you — go ahead and take the photo."
