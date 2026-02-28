from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from standupbot.config import AppConfig, TriggerConfig


@dataclass
class TriggerMatch:
    trigger: TriggerConfig
    matched_keyword: str
    response: str


class Analyzer:
    """Checks transcribed text for trigger keywords and generates responses via claude."""

    def __init__(self, config: AppConfig) -> None:
        self._triggers = config.triggers
        self._claude_model = config.claude.model
        self._user_context = config.user_context
        self._allowed_tools = config.claude.allowed_tools
        self._system_prompt = self._build_system_prompt(config)
        self._last_fired: dict[str, float] = {}
        self._transcript_history: list[str] = []

    @staticmethod
    def _build_system_prompt(config: AppConfig) -> str:
        """Build system prompt from user_context.

        CLAUDE.md and memories are loaded automatically by claude's default
        system prompt when using --append-system-prompt.
        """
        return config.user_context.strip() if config.user_context else ""

    def add_to_history(self, text: str) -> None:
        self._transcript_history.append(text)
        # Keep last ~20 utterances for context
        if len(self._transcript_history) > 20:
            self._transcript_history = self._transcript_history[-20:]

    def check_keywords(self, text: str) -> tuple[TriggerConfig, str] | None:
        """Fast substring match against all triggers, respecting cooldowns."""
        text_lower = text.lower()
        now = time.monotonic()

        for trigger in self._triggers:
            last = self._last_fired.get(trigger.name, 0.0)
            if now - last < trigger.cooldown_seconds:
                continue

            for keyword in trigger.keywords:
                if keyword.lower() in text_lower:
                    self._last_fired[trigger.name] = now
                    return trigger, keyword

        return None

    async def generate_response(self, trigger: TriggerConfig, transcript: str) -> str:
        """Call `claude -p` to generate a response."""
        context = "\n".join(self._transcript_history[-10:])
        prompt = (
            f"Recent meeting transcript:\n{context}\n\n"
            f"Latest utterance: {transcript}\n\n"
            f"{trigger.prompt}"
        )

        cmd = ["claude", "-p", prompt, "--model", self._claude_model]
        if self._system_prompt:
            cmd.extend(["--append-system-prompt", self._system_prompt])
        if self._allowed_tools:
            cmd.extend(["--allowedTools", ",".join(self._allowed_tools)])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            err = stderr.decode().strip()
            return f"[Claude error: {err}]"

        return stdout.decode().strip()

    async def analyze(self, text: str) -> TriggerMatch | None:
        """Check for triggers and generate a response if matched."""
        self.add_to_history(text)

        match = self.check_keywords(text)
        if match is None:
            return None

        trigger, keyword = match
        response = await self.generate_response(trigger, text)
        return TriggerMatch(trigger=trigger, matched_keyword=keyword, response=response)

    async def force_trigger(self, trigger: TriggerConfig) -> TriggerMatch:
        """Manually fire a trigger, bypassing cooldowns."""
        latest = self._transcript_history[-1] if self._transcript_history else ""
        response = await self.generate_response(trigger, latest)
        return TriggerMatch(trigger=trigger, matched_keyword="(manual)", response=response)
