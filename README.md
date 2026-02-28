# StandupBot

A meeting attendance bot that listens to your meetings, transcribes audio in real time with Whisper, and automatically responds when it hears trigger phrases — using Claude to generate natural, context-aware replies spoken back into the call.

## How It Works

```
Meeting audio → Multi-Output Device → Speakers (you hear)
                                    → BlackHole 2ch (bot captures)
                                    → Whisper transcription
                                    → Trigger keyword detection
                                    → Claude generates response
                                    → TTS (say or Kokoro) → BlackHole 2ch → meeting hears bot

You can speak over the bot at any time via your real microphone.
```

## Prerequisites

### macOS

This project only works on macOS. It relies on:
- CoreAudio for virtual audio routing
- The `say` command for text-to-speech (default engine), or Kokoro for neural TTS (optional)

### Python 3.12+

Check your version:

```sh
python3 --version
```

If you need to install or update, use [Homebrew](https://brew.sh):

```sh
brew install python@3.12
```

### uv (Python package manager)

```sh
brew install uv
```

### portaudio

Required by the `sounddevice` Python package for audio capture:

```sh
brew install portaudio
```

### BlackHole 2ch

BlackHole is a free, open-source virtual audio driver that creates a loopback device. The bot captures meeting audio through it, and speaks responses back through it.

Install via Homebrew:

```sh
brew install blackhole-2ch
```

Or download from: https://existential.audio/blackhole/

After installation, **restart your Mac** (or at minimum log out and back in) for the audio driver to load.

Verify it appears:

```sh
python3 -c "import sounddevice; print([d['name'] for d in sounddevice.query_devices() if 'blackhole' in d['name'].lower()])"
```

You should see `['BlackHole 2ch']`.

### Claude Code CLI

The bot calls `claude -p` to generate responses. Install Claude Code and authenticate:

```sh
npm install -g @anthropic-ai/claude-code
claude  # follow the authentication prompts
```

Verify it works:

```sh
claude -p "Say hello in one sentence"
```

## Audio Device Setup

You need two virtual audio devices configured in **Audio MIDI Setup** (Applications → Utilities → Audio MIDI Setup):

### 1. Multi-Output Device

Sends meeting audio to your speakers AND to BlackHole simultaneously so you can hear the meeting while the bot captures it.

**Automated setup:**

```sh
swift create_multi_output.swift
```

**Manual setup** (persists across reboots, unlike the script):

1. Open Audio MIDI Setup
2. Click the **+** button at the bottom left → **Create Multi-Output Device**
3. Check **MacBook Pro Speakers** (or your preferred output)
4. Check **BlackHole 2ch**
5. Make sure speakers are listed first (drag to reorder if needed)

### 2. Aggregate Device

Combines your real microphone with BlackHole so the meeting hears both you and the bot. You should already have this if you followed any BlackHole setup guide.

**Manual setup:**

1. Open Audio MIDI Setup
2. Click **+** → **Create Aggregate Device**
3. Check **MacBook Pro Microphone** (or your preferred mic)
4. Check **BlackHole 2ch**

### Meeting App Configuration

In your meeting app (Zoom, Google Meet, Teams, etc.):

| Setting    | Device               |
|------------|----------------------|
| Speaker    | Multi-Output Device  |
| Microphone | Aggregate Device     |

## Installation

Clone the repo and install dependencies:

```sh
cd standupbot
uv sync
```

The first time you run the app, Whisper will download the `base.en` model (~150 MB).

## Configuration

Edit `config.yaml` to customize behavior:

```yaml
audio:
  capture_device: "BlackHole 2ch"     # What the bot listens to
  playback_device: "BlackHole 2ch"    # Where the bot speaks into
  sample_rate: 16000                  # Whisper expects 16kHz

vad:
  energy_threshold: 0.01              # Raise if picking up background noise
  silence_duration_s: 1.5             # Seconds of silence before processing

whisper:
  model_size: "base.en"              # Options: tiny.en, base.en, small.en, medium.en

tts:
  engine: say                         # "say" (default) or "kokoro"
  voice: "Samantha"                   # macOS voice (run `say -v ?` to list all)
  rate: 175                           # Words per minute

claude:
  model: "sonnet"                     # Model flag passed to `claude -p --model`

user_context: |
  You are a helpful assistant attending a meeting on behalf of the user.
  Keep responses brief and natural-sounding (1-3 sentences).

triggers:
  - name: standup_update
    keywords: ["your update", "your turn", "what about you", "go ahead"]
    prompt: |
      Give a brief standup update (2-3 sentences).
    cooldown_seconds: 60

  - name: direct_question
    keywords: ["what do you think", "do you agree", "any thoughts"]
    prompt: |
      Give a brief, thoughtful response (1-2 sentences).
    cooldown_seconds: 30
```

### Triggers

Each trigger has:
- **keywords** — if any keyword appears in transcribed speech (case-insensitive), the trigger fires
- **prompt** — sent to Claude along with recent transcript context
- **cooldown_seconds** — minimum time between consecutive firings of the same trigger

### TTS Engine

By default, StandupBot uses macOS `say` for text-to-speech (zero extra dependencies). You can optionally switch to **Kokoro TTS** ([hexgrad/Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M)), a small 82M-parameter neural TTS model that sounds significantly more natural. It's Apache 2.0 licensed and runs well on Apple Silicon.

**Install Kokoro dependencies:**

```sh
uv pip install -e ".[kokoro]"
```

**Enable in `config.yaml`:**

```yaml
tts:
  engine: kokoro
  voice: "af_heart"     # Kokoro voice ID
```

The Kokoro model weights are downloaded from HuggingFace on first run and cached locally. You can audition voices in the [live demo](https://huggingface.co/spaces/hexgrad/Kokoro-TTS) before picking one.

| Config field | Default | Description |
|---|---|---|
| `engine` | `say` | `"say"` for macOS TTS, `"kokoro"` for neural TTS |
| `voice` | `Samantha` | Voice name — macOS voice for `say`, voice ID for `kokoro` |
| `rate` | `175` | Words per minute (`say` only) |
| `kokoro_repo_id` | `hexgrad/Kokoro-82M` | HuggingFace repo ID (`kokoro` only) |
| `kokoro_lang_code` | `a` | Language code — must match the first letter of the voice ID (`kokoro` only) |

#### Kokoro Voice IDs

Voice IDs follow the pattern `{lang}{gender}_{name}` — first letter is the language code, second is `f` (female) or `m` (male).

- **American English** (`kokoro_lang_code: a`) — `af_heart` `af_alloy` `af_aoede` `af_bella` `af_jessica` `af_kore` `af_nicole` `af_nova` `af_river` `af_sarah` `af_sky` `am_adam` `am_echo` `am_eric` `am_fenrir` `am_liam` `am_michael` `am_onyx` `am_puck` `am_santa`
- **British English** (`kokoro_lang_code: b`) — `bf_alice` `bf_emma` `bf_isabella` `bf_lily` `bm_daniel` `bm_fable` `bm_george` `bm_lewis`
- **Japanese** (`kokoro_lang_code: j`) — `jf_alpha` `jf_gongitsune` `jf_nezumi` `jf_tebukuro` `jm_kumo`
- **Mandarin Chinese** (`kokoro_lang_code: z`) — `zf_xiaobei` `zf_xiaoni` `zf_xiaoxiao` `zf_xiaoyi` `zm_yunjian` `zm_yunxi` `zm_yunxia` `zm_yunyang`
- **Spanish** (`kokoro_lang_code: e`) — `ef_dora` `em_alex` `em_santa`
- **French** (`kokoro_lang_code: f`) — `ff_siwis`
- **Hindi** (`kokoro_lang_code: h`) — `hf_alpha` `hf_beta` `hm_omega` `hm_psi`
- **Italian** (`kokoro_lang_code: i`) — `if_sara` `im_nicola`
- **Brazilian Portuguese** (`kokoro_lang_code: p`) — `pf_dora` `pm_alex` `pm_santa`

## Usage

```sh
uv run standupbot
```

Or with a custom config path:

```sh
uv run standupbot /path/to/config.yaml
```

### TUI Controls

| Key       | Action                                              |
|-----------|-----------------------------------------------------|
| `p`       | Pause / Resume audio capture                        |
| `t`       | Toggle auto-triggers on / off                       |
| `1`..`9`  | Manually fire a trigger (number shown in status bar) |
| `c`       | Clear logs                                          |
| `q`       | Quit                                                |

The left panel shows live transcription. The right panel shows bot responses and which trigger fired.

The status bar at the bottom shows the current state (Listening / Paused), whether auto-triggers are ON or OFF, and a numbered list of available triggers (e.g. `1=standup_update  2=direct_question`).

### Auto-triggers vs Manual Triggers

By default, auto-triggers are **on** — the bot watches every transcribed utterance for keyword matches and responds automatically.

Press `t` to turn auto-triggers **off**. Transcription and history still accumulate, but the bot won't respond on its own. You can then press a number key (e.g. `1`) at any time to manually fire a specific trigger using the recent transcript as context. Manual triggers bypass cooldowns.

## Troubleshooting

### "Failed to open audio device"

- Make sure BlackHole 2ch is installed and you've restarted since installing
- Run `python -c "import sounddevice; print(sounddevice.query_devices())"` and verify `BlackHole 2ch` appears
- Check that the device name in `config.yaml` matches exactly

### Bot is picking up its own responses (feedback loop)

The bot pauses audio capture while speaking. If you're still getting loops:
- Make sure your meeting app's **microphone** is set to the Aggregate Device (not BlackHole directly)
- Increase `vad.energy_threshold` in config

### Whisper transcription is poor

- Try a larger model: `small.en` or `medium.en` (slower but more accurate)
- Ensure `sample_rate` is 16000

### Claude errors

- Run `claude -p "test"` manually to verify authentication
- Check that the `claude.model` value in config is valid

### Multi-Output Device disappeared after reboot

The `swift create_multi_output.swift` script creates an ephemeral device. Either:
- Re-run the script after each reboot
- Create the device manually in Audio MIDI Setup (manual devices persist)
