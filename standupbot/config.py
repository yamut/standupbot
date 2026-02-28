from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class AudioConfig:
    capture_device: str = "BlackHole 2ch"
    playback_device: str = "BlackHole 2ch"
    local_playback_device: str = ""
    sample_rate: int = 16000


@dataclass
class VADConfig:
    energy_threshold: float = 0.01
    silence_duration_s: float = 1.5


@dataclass
class WhisperConfig:
    model_size: str = "base.en"


@dataclass
class TTSConfig:
    engine: str = "say"                       # "say" or "kokoro"
    voice: str = "Samantha"                   # say voice name, or kokoro voice (e.g. "af_heart")
    rate: int = 175                           # say only
    kokoro_repo_id: str = "hexgrad/Kokoro-82M"  # HuggingFace repo ID
    kokoro_lang_code: str = "a"               # "a" = American English


@dataclass
class ClaudeConfig:
    model: str = "sonnet"
    allowed_tools: list[str] = field(default_factory=list)


@dataclass
class TriggerConfig:
    name: str = ""
    keywords: list[str] = field(default_factory=list)
    prompt: str = ""
    cooldown_seconds: int = 60


@dataclass
class AppConfig:
    audio: AudioConfig = field(default_factory=AudioConfig)
    vad: VADConfig = field(default_factory=VADConfig)
    whisper: WhisperConfig = field(default_factory=WhisperConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    claude: ClaudeConfig = field(default_factory=ClaudeConfig)
    user_context: str = ""
    triggers: list[TriggerConfig] = field(default_factory=list)


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    path = Path(path)
    if not path.exists():
        return AppConfig()

    raw = yaml.safe_load(path.read_text()) or {}

    config = AppConfig(
        audio=AudioConfig(**raw.get("audio", {})),
        vad=VADConfig(**raw.get("vad", {})),
        whisper=WhisperConfig(**raw.get("whisper", {})),
        tts=TTSConfig(**raw.get("tts", {})),
        claude=ClaudeConfig(**raw.get("claude", {})),
        user_context=raw.get("user_context", ""),
        triggers=[TriggerConfig(**t) for t in raw.get("triggers", [])],
    )
    return config
