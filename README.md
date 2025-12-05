# Whispering

Real-time speech transcription and translation using [faster-whisper](https://github.com/SYSTRAN/faster-whisper) and Google Translate. Available in a modern Web/Native UI, Legacy Tkinter GUI, and TUI versions.

## Quick Start

```bash
git clone https://github.com/Jemtaly/Whispering.git
cd Whispering
./scripts/install.sh       # Install dependencies
./scripts/run_nicegui.sh   # Run the new Modern UI
```

## Features

- **Modern Dark Theme UI** - New interface built with NiceGUI, featuring a professional dark theme and compact layout
- **Native Window Support** - Runs as a native desktop application (via PyQt6/pywebview) or in your web browser
- **Real-time transcription** with iterative refinement for accuracy
- **AI-powered text processing** - intelligent proofreading and translation with OpenRouter integration
- **Text-to-Speech (TTS)** - convert transcribed text back to audio with voice cloning support
  - **New:** Upload reference audio files directly in the UI for voice cloning
- **Transcript logging** - automatic session-based logging to timestamped files
- **Live translation** to 100+ languages via Google Translate or AI models
- **Auto-type to any app** - dictate directly into browsers, editors, chat apps
- **Clipboard integration** - Copy and Cut buttons for all output panels
- **Smart window management** - Sidebar layout with dynamic text panel visibility
- **Settings persistence** - remembers preferences including layout, models, and voices
- **GPU acceleration** with CUDA support for fast inference
- **Contextual help** - built-in help dialogs for all major features

## Requirements

- Python 3.8+
- Linux with PipeWire or PulseAudio (recommended)
- NVIDIA GPU with CUDA 12 (optional, for GPU acceleration)
- **New UI Requirements:** `nicegui`, `pyperclip`, `pywebview` (optional), `PyQt6` (optional)

## Installation

### Quick Install (Recommended)

```bash
# Clone the repository
git clone https://github.com/Jemtaly/Whispering.git
cd Whispering

# Run the installation script
./scripts/install.sh
```

The install script will:
- Check Python version
- Create a virtual environment
- Install all dependencies (including new UI requirements)
- Optionally install CUDA libraries

### Manual Installation

```bash
# Clone the repository
git clone https://github.com/Jemtaly/Whispering.git
cd Whispering

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# For Native Window support (Optional)
pip install pywebview PyQt6 PyQt6-WebEngine

# For CUDA support (Optional)
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12

# Create necessary directories
mkdir -p log_output tts_output tts_voices

# Copy environment template
cp config/.env.example .env
```

## Usage

### Modern UI (NiceGUI)

This is the new standard interface featuring a dark theme and improved layout.

```bash
./scripts/run_nicegui.sh
```

**Interface Layout:**
- **Sidebar (Left):** Contains all controls (Model, AI, TTS, Settings).
- **Output Panels (Right):** Three dynamic text areas (Whisper, AI, Translation).
- **Visibility:** Click "Show/Hide Text" to toggle the output panels.
- **Native Mode:** If PyQt6 is installed, the app opens in a standalone window. Otherwise, it launches in your default web browser.

**Key Features:**
- **TTS Voice Upload:** In the TTS section, you can now drag and drop or browse for audio files (wav/mp3/ogg, max 50MB) to use as voice references.
- **Compact Styling:** The interface uses "dense" mode to maximize screen space.
- **Help System:** Click the **?** button next to any section header for detailed usage instructions.
- **Manual AI Mode:** Toggle "Manual Mode" to queue text and process it only when you click "Process NOW".

### Legacy GUI (Tkinter)

The classic two-column interface is still available.

```bash
./scripts/run_tkinter.sh
```

**Legacy Layout:**
- **Left column:** Controls
- **Right column:** Three text windows
- **Minimal mode:** Starts compact (400x950px), expandable via "Show Text".

### TUI (Terminal User Interface)

```bash
python src/tui.py [options]
```

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--mic` | auto | Microphone device name (partial match) |
| `--model` | large-v3 | Model: tiny, base, small, medium, large-v1/v2/v3 |
| `--device` | cuda | Inference device: cpu, cuda, auto |
| `--vad` | off | Enable voice activity detection |

## AI Features (Optional)

Whispering includes powerful AI-powered text processing capabilities:

- **Intelligent Proofreading** - Fix spelling, grammar, and punctuation
- **Context-Aware Translation** - Better translations that understand speech patterns
- **Multiple AI Models** - Support for Claude, GPT-4, Gemini, Llama via OpenRouter
- **Trigger Modes**:
  - **Automatic:** Process based on time intervals or word count.
  - **Manual:** Accumulate text and process on demand.

See [AI_SETUP.md](AI_SETUP.md) for setup instructions.

## Text-to-Speech (TTS) Features (Optional)

Convert your transcribed text back to audio:

- **Session-based audio generation**
- **Voice cloning support** via file upload or selection
- **Output formats:** WAV or OGG
- **ChatterboxTTS integration**

See [INSTALL_TTS.md](INSTALL_TTS.md) for installation instructions.

## Auto-Type Feature

The auto-type feature allows you to dictate directly into other applications.

1. Select your desired mode (Whisper, Translation, or AI) from the auto-type dropdown.
2. Click **Start**.
3. Focus the target window (editor, browser, etc.).
4. Speak.

**Requirements:**
- Linux X11: `sudo apt install xdotool xclip`
- Linux Wayland: `sudo apt install wtype wl-clipboard`
- Windows/macOS: `pip install pyautogui`

## Session Logging (New)

Whispering now includes comprehensive session logging with automatic crash recovery:

**Features:**
- **JSONL Format** - Readable and parsable log files with complete session data
- **Automatic Crash Recovery** - Detects and prompts to recover incomplete sessions on startup
- **Organized Storage** - Logs organized by date: `logs/YYYY/MM/DD/`
- **Request ID System** - Unique session identifiers in format `2YMMDDNNNN`
- **5MB File Size Limit** - Automatic rollover when files reach size limit
- **Complete Configuration Logging** - Saves all settings and outputs for each session
- **Multiple Stop Reasons** - Tracks manual, auto-stop, error, and unexpected shutdowns

**Settings:**
- Toggle logging in sidebar: "Save logs" checkbox
- Configurable max file size (default 5MB)
- Settings persist across sessions
- User choice on crash recovery: Recover or Discard

**Log Content:**
- Session start/end timestamps with duration
- Complete configuration snapshot (model, AI settings, TTS, etc.)
- All text outputs (Whisper, AI, Translation)
- Stop reason classification
- Request ID for session tracking

**File Structure:**
```
logs/
├── 2025/
│   ├── 01/
│   │   ├── 2501010001.jsonl      # Session 1
│   │   ├── 2501010002.jsonl      # Session 2
│   │   ├── 2501010003.jsonl      # Session 3
│   │   └── .temp_2501010004.jsonl  # Crashed session (recovery pending)
│   └── ...
```

**Recovery Process:**
1. App startup scans for `.temp_*.jsonl` files
2. Shows dialog: "Found incomplete session from [timestamp]. Recover or Discard?"
3. User choice moves temp file to permanent location or deletes it
4. Final log file contains complete session data with proper timestamps

## File Structure

```
Whispering/
├── src/
│   ├── whispering_ui/      # New NiceGUI application package
│   │   ├── components/     # UI Components (Sidebar, Output)
│   │   ├── state.py        # UI State management
│   │   ├── bridge.py       # Logic bridge
│   │   └── main.py         # Entry point
│   ├── gui.py              # Legacy Tkinter application
│   ├── tui.py              # TUI application
│   ├── core.py             # Core transcription logic
│   └── ...
├── config/                 # Configuration files
├── scripts/                # Launchers (run_nicegui.sh, run_tkinter.sh)
├── log_output/             # Transcripts
├── tts_output/             # Generated Audio
└── tts_voices/             # Uploaded voice references
```

## License

MIT License

## Acknowledgments

- [NiceGUI](https://nicegui.io/) - Web-based UI framework
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) - Fast Whisper implementation
- [OpenAI Whisper](https://github.com/openai/whisper) - Original speech recognition model
- [Google Translate](https://translate.google.com/) - Translation service
