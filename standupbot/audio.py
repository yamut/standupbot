from __future__ import annotations

import asyncio
import queue
from collections.abc import AsyncIterator

import numpy as np
import sounddevice as sd

from standupbot.config import AudioConfig, VADConfig


class AudioCapture:
    """Captures audio from a PortAudio device and yields complete utterances."""

    def __init__(
        self,
        audio_cfg: AudioConfig,
        vad_cfg: VADConfig,
        speaking_event: asyncio.Event,
    ) -> None:
        self._device = audio_cfg.capture_device
        self._sample_rate = audio_cfg.sample_rate
        self._energy_threshold = vad_cfg.energy_threshold
        self._silence_duration = vad_cfg.silence_duration_s
        self._speaking_event = speaking_event  # set while bot is speaking
        self._queue: queue.Queue[np.ndarray] = queue.Queue()
        self._stream: sd.InputStream | None = None

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: object,
        status: sd.CallbackFlags,
    ) -> None:
        """Called by PortAudio on its own thread."""
        if self._speaking_event.is_set():
            return  # skip frames while bot is speaking
        self._queue.put(indata.copy())

    def start(self) -> None:
        self._stream = sd.InputStream(
            device=self._device,
            samplerate=self._sample_rate,
            channels=1,
            dtype="float32",
            blocksize=1024,
            callback=self._audio_callback,
        )
        self._stream.start()

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    async def utterances(self) -> AsyncIterator[np.ndarray]:
        """Yields complete utterances as float32 numpy arrays.

        Uses energy-based VAD: accumulates audio while energy is above threshold,
        yields the accumulated buffer after silence_duration_s of quiet.
        """
        loop = asyncio.get_running_loop()
        buffer: list[np.ndarray] = []
        silence_samples = 0
        silence_threshold = int(self._silence_duration * self._sample_rate)

        while True:
            try:
                chunk = await loop.run_in_executor(None, self._queue.get, True, 0.1)
            except queue.Empty:
                continue

            energy = float(np.sqrt(np.mean(chunk ** 2)))

            if energy >= self._energy_threshold:
                buffer.append(chunk)
                silence_samples = 0
            elif buffer:
                silence_samples += len(chunk)
                buffer.append(chunk)  # include trailing silence for natural cutoff

                if silence_samples >= silence_threshold:
                    utterance = np.concatenate(buffer).flatten()
                    buffer.clear()
                    silence_samples = 0
                    yield utterance
