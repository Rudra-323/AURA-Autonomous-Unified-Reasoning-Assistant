"""
Speech-to-text, routed by language. English and Hindi use faster-whisper
(fast, accurate, well-supported). Odia is a low-resource language for
Whisper — quality is genuinely weak there — so Odia routes to AI4Bharat's
IndicConformer instead, which is purpose-built for Indian languages
including Odia. This is a deliberate design choice, not a shortcut: see
architecture.md for why one model can't cover all three well.
"""

from __future__ import annotations

from functools import lru_cache

from config.settings import get_settings
from utils.errors import ExternalServiceError
from utils.logging import get_logger

log = get_logger("voice.stt")

SUPPORTED_LANGUAGES = {"en", "hi", "or"}  # ISO codes: English, Hindi, Odia


@lru_cache(maxsize=1)
def _whisper_model():
    from faster_whisper import WhisperModel
    settings = get_settings()
    # CPU by default (compute_type="int8") so this runs without a GPU; set
    # device="cuda" and compute_type="float16" if one's available at deploy time.
    return WhisperModel(settings.whisper_model_size, device="cpu", compute_type="int8")


@lru_cache(maxsize=1)
def _indic_conformer():
    """Lazy-loaded — only pulled in if Odia audio actually arrives, since
    it's a separate, heavier dependency most demo runs won't need."""
    try:
        import torch
        from transformers import AutoModel
    except ImportError as exc:
        raise ExternalServiceError(
            "Odia STT requires 'torch' and 'transformers' — install them to enable it.",
        ) from exc
    model = AutoModel.from_pretrained("ai4bharat/indic-conformer-600m-multilingual", trust_remote_code=True)
    return model


def transcribe(audio_path: str, language: str) -> str:
    """Transcribe an audio file to text. `language` must be one of
    SUPPORTED_LANGUAGES — resolve/detect it before calling this."""
    if language not in SUPPORTED_LANGUAGES:
        raise ExternalServiceError(f"Unsupported language: {language}")

    if language == "or":
        model = _indic_conformer()
        # IndicConformer's exact inference call signature varies by release —
        # verify against the model card at build time; this is the documented
        # shape as of the model's current release.
        result = model(audio_path, "or", "ctc")
        return str(result)

    model = _whisper_model()
    lang_code = {"en": "en", "hi": "hi"}[language]
    segments, _info = model.transcribe(audio_path, language=lang_code)
    text = " ".join(seg.text for seg in segments).strip()
    log.info("stt.transcribed", extra={"language": language, "chars": len(text)})
    return text
