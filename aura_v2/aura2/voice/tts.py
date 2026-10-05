"""
Text-to-speech, routed by language.

English/Hindi use `edge-tts` — Microsoft's free neural TTS service. Chosen
over Coqui TTS specifically because Coqui requires compiling a Cython
extension (`monotonic_align`), which needs a C++ build toolchain and fails
on a stock Windows machine. edge-tts is pure Python, pip-installable, has
good Hindi voices, and needs no compiler — much better fit for a project
meant to be easy to actually run.

Odia still uses AI4Bharat's Indic-TTS, since it's genuinely one of the only
open options with real Odia support — see the module docstring in stt.py
for why one model can't cover all three languages well.
"""

from __future__ import annotations

from pathlib import Path

from utils.errors import ExternalServiceError
from utils.logging import get_logger
from voice.stt import SUPPORTED_LANGUAGES

log = get_logger("voice.tts")

# Edge neural voices — picked for naturalness; swap freely, run
# `edge-tts --list-voices` to see all available options.
_EDGE_VOICES = {
    "en": "en-US-AriaNeural",
    "hi": "hi-IN-SwaraNeural",
}


async def _synthesize_edge(text: str, language: str, output_path: str) -> None:
    import edge_tts
    communicate = edge_tts.Communicate(text, _EDGE_VOICES[language])
    await communicate.save(output_path)


def _indic_tts_odia():
    """AI4Bharat Indic-TTS (FastPitch + HiFi-GAN) isn't pip-installable the
    way edge-tts is — it requires cloning the inference repo. See
    architecture.md > Voice for the one-time setup steps. Raises until
    that's done, rather than silently producing nothing."""
    raise ExternalServiceError(
        "Odia TTS requires the AI4Bharat Indic-TTS inference setup — "
        "see architecture.md > Voice for the one-time install steps."
    )


async def synthesize(text: str, language: str, output_path: str) -> str:
    """Synthesize `text` to speech, writing an audio file to output_path.
    Async natively (edge-tts is an async client) — call directly with
    `await`, no thread-offloading needed the way Coqui's sync API required."""
    if language not in SUPPORTED_LANGUAGES:
        raise ExternalServiceError(f"Unsupported language: {language}")
    if not text.strip():
        raise ExternalServiceError("Nothing to synthesize")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if language == "or":
        _indic_tts_odia()  # always raises for now — see docstring above
    else:
        try:
            await _synthesize_edge(text, language, output_path)
        except Exception as exc:  # noqa: BLE001 — edge-tts raises its own network/service errors
            raise ExternalServiceError(f"edge-tts synthesis failed: {exc}") from exc

    log.info("tts.synthesized", extra={"language": language, "chars": len(text)})
    return output_path
