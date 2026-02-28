from __future__ import annotations

import asyncio
import functools
import logging
from typing import TYPE_CHECKING

import numpy as np

from standupbot.config import AudioConfig, TTSConfig

if TYPE_CHECKING:
    from kokoro import KPipeline

log = logging.getLogger(__name__)


class SaySpeaker:
    """Speaks text via macOS `say` routed through BlackHole."""

    def __init__(
        self,
        tts_cfg: TTSConfig,
        audio_cfg: AudioConfig,
        speaking_event: asyncio.Event,
    ) -> None:
        self._voice = tts_cfg.voice
        self._rate = str(tts_cfg.rate)
        self._device = audio_cfg.playback_device
        self._local_device = audio_cfg.local_playback_device
        self._speaking_event = speaking_event

    async def _say_on_device(self, text: str, device: str) -> None:
        proc = await asyncio.create_subprocess_exec(
            "say",
            "-v", self._voice,
            "-r", self._rate,
            "-a", device,
            text,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()

    async def speak(self, text: str) -> None:
        """Speak text through configured devices. Sets speaking_event during playback."""
        self._speaking_event.set()
        try:
            tasks = [self._say_on_device(text, self._device)]
            if self._local_device:
                tasks.append(self._say_on_device(text, self._local_device))
            await asyncio.gather(*tasks)
        finally:
            self._speaking_event.clear()


class KokoroSpeaker:
    """Speaks text via Kokoro TTS, played through sounddevice."""

    SAMPLE_RATE = 24000

    def __init__(
        self,
        tts_cfg: TTSConfig,
        audio_cfg: AudioConfig,
        speaking_event: asyncio.Event,
        pipeline: KPipeline | None = None,
    ) -> None:
        self._voice = tts_cfg.voice
        self._lang_code = tts_cfg.kokoro_lang_code
        self._repo_id = tts_cfg.kokoro_repo_id
        self._device = audio_cfg.playback_device
        self._local_device = audio_cfg.local_playback_device
        self._speaking_event = speaking_event
        self._pipeline = pipeline

    def load_model(self) -> None:
        """Load the Kokoro pipeline if not already pre-loaded."""
        if self._pipeline is not None:
            return
        try:
            from kokoro import KPipeline
        except ModuleNotFoundError:
            raise ModuleNotFoundError(
                "Kokoro TTS requires the 'kokoro' package. "
                "Install it with: uv pip install -e \".[kokoro]\""
            )
        self._pipeline = KPipeline(lang_code=self._lang_code, repo_id=self._repo_id)

    def _generate_audio(self, text: str) -> np.ndarray:
        """Generate audio from text synchronously. Returns a numpy array."""
        assert self._pipeline is not None, "Call load_model() first"
        chunks: list[np.ndarray] = []
        for _, _, audio in self._pipeline(text, voice=self._voice):
            if audio is not None:
                chunks.append(audio)
        if not chunks:
            return np.array([], dtype=np.float32)
        return np.concatenate(chunks)

    @staticmethod
    def _play_on_device_sync(audio: np.ndarray, sample_rate: int, device: str) -> None:
        """Play audio on a specific device. Each call gets its own OutputStream."""
        import sounddevice as sd

        stereo = np.column_stack([audio, audio])
        with sd.OutputStream(samplerate=sample_rate, channels=2, device=device) as stream:
            stream.write(stereo)

    async def _play_on_device(self, audio: np.ndarray, device: str) -> None:
        """Play audio array on a specific device using sounddevice."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, self._play_on_device_sync, audio, self.SAMPLE_RATE, device
        )

    async def speak(self, text: str) -> None:
        """Generate audio, then play through configured devices.

        speaking_event is set only during playback, not during generation.
        """
        loop = asyncio.get_running_loop()
        audio = await loop.run_in_executor(None, self._generate_audio, text)
        if audio.size == 0:
            return

        self._speaking_event.set()
        try:
            tasks = [self._play_on_device(audio, self._device)]
            if self._local_device:
                tasks.append(self._play_on_device(audio, self._local_device))
            await asyncio.gather(*tasks)
        finally:
            self._speaking_event.clear()


def create_speaker(
    tts_cfg: TTSConfig,
    audio_cfg: AudioConfig,
    speaking_event: asyncio.Event,
    kokoro_pipeline: KPipeline | None = None,
) -> SaySpeaker | KokoroSpeaker:
    """Factory: return the right speaker based on config."""
    if tts_cfg.engine == "kokoro":
        speaker = KokoroSpeaker(
            tts_cfg, audio_cfg, speaking_event, pipeline=kokoro_pipeline
        )
        speaker.load_model()
        return speaker
    return SaySpeaker(tts_cfg, audio_cfg, speaking_event)
