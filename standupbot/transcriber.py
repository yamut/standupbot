from __future__ import annotations

import asyncio
from functools import partial

import numpy as np
from faster_whisper import WhisperModel

from standupbot.config import WhisperConfig


class Transcriber:
    """Wraps faster-whisper for async transcription."""

    def __init__(self, cfg: WhisperConfig) -> None:
        self._model_size = cfg.model_size
        self._model: WhisperModel | None = None

    def load_model(self) -> None:
        self._model = WhisperModel(self._model_size, device="cpu", compute_type="int8")

    def _transcribe_sync(self, audio: np.ndarray) -> str:
        assert self._model is not None
        segments, _info = self._model.transcribe(audio, beam_size=3, language="en")
        return " ".join(seg.text.strip() for seg in segments).strip()

    async def transcribe(self, audio: np.ndarray) -> str:
        """Run whisper inference in a thread pool to avoid blocking the event loop."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(self._transcribe_sync, audio))
