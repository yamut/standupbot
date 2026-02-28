from __future__ import annotations

import asyncio
import sys

from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Footer, Header, RichLog

from standupbot.analyzer import Analyzer, TriggerMatch
from standupbot.audio import AudioCapture
from standupbot.config import load_config
from standupbot.speaker import KokoroSpeaker, SaySpeaker, create_speaker
from standupbot.transcriber import Transcriber


class StandupBotApp(App):
    """Textual TUI for the standup bot."""

    TITLE = "StandupBot"
    CSS = """
    Screen {
        layout: vertical;
    }
    #panels {
        height: 1fr;
    }
    #transcript {
        width: 1fr;
        border: solid $primary;
        border-title-color: $text;
    }
    #responses {
        width: 1fr;
        border: solid $success;
        border-title-color: $text;
        border-subtitle-color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("p", "toggle_pause", "Pause/Resume"),
        Binding("t", "toggle_triggers", "Triggers On/Off"),
        Binding("c", "clear_logs", "Clear"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        config_path: str = "config.yaml",
        transcriber: Transcriber | None = None,
        kokoro_pipeline: object | None = None,
    ) -> None:
        super().__init__()
        self._config = load_config(config_path)
        self._transcriber = transcriber
        self._kokoro_pipeline = kokoro_pipeline
        self._paused = asyncio.Event()  # clear = paused, set = running
        self._paused.set()
        self._speaking = asyncio.Event()
        self._capture: AudioCapture | None = None
        self._triggers_enabled = False
        self._analyzer: Analyzer | None = None
        self._speaker: SaySpeaker | KokoroSpeaker | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="panels"):
            transcript = RichLog(id="transcript", wrap=True, markup=True)
            transcript.border_title = "Transcript"
            yield transcript
            responses = RichLog(id="responses", wrap=True, markup=True)
            responses.border_title = "Bot Responses"
            yield responses
        yield Footer()

    def on_mount(self) -> None:
        responses_log = self.query_one("#responses", RichLog)
        responses_log.write("[bold]Available triggers:[/]")
        for i, trigger in enumerate(self._config.triggers):
            keywords = ", ".join(trigger.keywords)
            responses_log.write(f"  [bold]{i + 1}[/] {trigger.name} [dim]({keywords})[/]")
        responses_log.write("")
        self._update_chrome()
        self._run_pipeline()

    @work(exclusive=True)
    async def _run_pipeline(self) -> None:
        transcript_log = self.query_one("#transcript", RichLog)

        # Use pre-loaded transcriber (model loaded on main thread before TUI starts)
        assert self._transcriber is not None
        transcriber = self._transcriber

        # Init components
        self._analyzer = Analyzer(self._config)
        self._speaker = create_speaker(
            self._config.tts, self._config.audio, self._speaking,
            kokoro_pipeline=self._kokoro_pipeline,
        )
        analyzer = self._analyzer
        self._capture = AudioCapture(
            self._config.audio, self._config.vad, self._speaking
        )

        # Start audio capture
        try:
            self._capture.start()
        except Exception as e:
            self.sub_title = "Audio error!"
            transcript_log.write(
                f"[red]Failed to open audio device '{self._config.audio.capture_device}': {e}[/]"
            )
            return

        self._update_chrome()

        try:
            async for utterance in self._capture.utterances():
                # Check pause
                await self._paused.wait()

                self.sub_title = "Transcribing..."
                text = await transcriber.transcribe(utterance)
                if not text or len(text.strip()) < 3:
                    self._update_chrome()
                    continue

                transcript_log.write(f"[dim]{text}[/]")

                # Check triggers (only if auto-triggers enabled)
                if self._triggers_enabled:
                    keyword_match = analyzer.check_keywords(text)
                    if keyword_match:
                        trigger, keyword = keyword_match
                        responses_log = self.query_one("#responses", RichLog)
                        responses_log.write(
                            f"[bold yellow]Triggered:[/] [bold cyan]{trigger.name}[/] "
                            f"[dim](matched: '{keyword}')[/]"
                        )
                        self.sub_title = f"Generating response for {trigger.name}..."
                        analyzer.add_to_history(text)
                        response = await analyzer.generate_response(trigger, text)
                        result = TriggerMatch(trigger=trigger, matched_keyword=keyword, response=response)
                    else:
                        analyzer.add_to_history(text)
                        result = None
                else:
                    analyzer.add_to_history(text)
                    result = None

                if result is not None:
                    await self._handle_trigger_result(result)
                else:
                    self._update_chrome()
        finally:
            self._capture.stop()

    def _update_chrome(self) -> None:
        """Update header subtitle and responses panel border to reflect current state."""
        # Header subtitle: listening state
        if self._paused.is_set():
            state = "Listening"
        else:
            state = "Paused"

        trigger_label = "ON" if self._triggers_enabled else "OFF"
        self.sub_title = f"{state} | Auto-triggers: {trigger_label}"

        # Responses panel border title
        responses = self.query_one("#responses", RichLog)
        if self._triggers_enabled:
            responses.border_title = "Bot Responses [Triggers ON]"
        else:
            responses.border_title = "Bot Responses [Triggers OFF]"

        # Subtitle on responses panel: numbered trigger shortcuts
        hints = "  ".join(f"{i + 1}={t.name}" for i, t in enumerate(self._config.triggers))
        responses.border_subtitle = hints

    async def _handle_trigger_result(self, result: TriggerMatch) -> None:
        responses_log = self.query_one("#responses", RichLog)
        responses_log.write(
            f"[bold cyan]\\[{result.trigger.name}][/] "
            f"[dim](matched: '{result.matched_keyword}')[/]"
        )
        responses_log.write(result.response)
        responses_log.write("")

        self.sub_title = "Speaking..."
        assert self._speaker is not None
        await self._speaker.speak(result.response)
        self._update_chrome()

    def action_toggle_pause(self) -> None:
        if self._paused.is_set():
            self._paused.clear()
        else:
            self._paused.set()
        self._update_chrome()

    def action_toggle_triggers(self) -> None:
        self._triggers_enabled = not self._triggers_enabled
        self._update_chrome()

    async def on_key(self, event: events.Key) -> None:
        if event.character and event.character.isdigit():
            idx = int(event.character) - 1
            if 0 <= idx < len(self._config.triggers) and self._analyzer is not None:
                event.prevent_default()
                event.stop()
                trigger = self._config.triggers[idx]
                self.sub_title = f"Generating response for {trigger.name}..."
                result = await self._analyzer.force_trigger(trigger)
                await self._handle_trigger_result(result)

    def action_clear_logs(self) -> None:
        self.query_one("#transcript", RichLog).clear()
        self.query_one("#responses", RichLog).clear()


def main() -> None:
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    config = load_config(config_path)

    # Load Whisper model on the main thread before Textual starts.
    # huggingface_hub's tqdm creates multiprocessing locks that crash
    # inside Textual's async worker thread pool.
    print(f"Loading Whisper model ({config.whisper.model_size})...")
    transcriber = Transcriber(config.whisper)
    transcriber.load_model()
    print("Model loaded.")

    # Pre-load Kokoro pipeline on the main thread for the same reason.
    kokoro_pipeline = None
    if config.tts.engine == "kokoro":
        print(f"Loading Kokoro TTS model ({config.tts.kokoro_repo_id})...")
        from kokoro import KPipeline

        kokoro_pipeline = KPipeline(
            lang_code=config.tts.kokoro_lang_code, repo_id=config.tts.kokoro_repo_id
        )
        print("Kokoro model loaded.")

    app = StandupBotApp(
        config_path=config_path,
        transcriber=transcriber,
        kokoro_pipeline=kokoro_pipeline,
    )
    app.run()


if __name__ == "__main__":
    main()
