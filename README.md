# Whispering 🎙️

Real-time speech-to-text application with AI-powered translation, proofreading, and voice cloning.

Whispering combines [faster-whisper](https://github.com/SYSTRAN/faster-whisper) for state-of-the-art speech recognition with modern AI models (Claude, GPT-4, Llama) to provide a powerful voice interface for your workflow.

##  Key Features

###  Transcription & Translation
- **Real-time Transcription**: Fast and accurate speech-to-text using Whisper models.
- **Live Translation**: Translate speech to 100+ languages instantly.
- **Auto-Type**: Dictate directly into any application (Word, Browser, IDE, Discord).
- **Smart Formatting**: Paragraph detection and automatic punctuation.

###  AI Powers
- **Intelligent Proofreading**: correct grammar and polish your spoken text.
- **Context-Aware Translation**: Nuanced translations that understand context.
- **Custom Personas**: Create specific AI assistants (e.g., "Summarize this", "Start a Story", "Q&A Mode").
- **Multi-Model Support**: Use Claude 3.5, GPT-4, Gemini, or Llama via OpenRouter.

###  Text-to-Speech (TTS)
- **Voice Cloning**: Upload a 5-second audio sample to clone any voice.
- **Read Aloud**: Listen to your transcripts or AI responses.
- **Save Audio**: Export generated speech to WAV/OGG files.

###  Session Management
- **Automatic Logging**: Secure JSONL logging of all sessions.
- **Crash Recovery**: Never lose a transcript, even if the app closes unexpectedly.
- **History**: Review past sessions organized by date.

##  Quick Start

### Installation

```bash
git clone https://github.com/Jemtaly/Whispering.git
cd Whispering
./scripts/install.sh
```

### Running the App

**Modern UI (Recommended)**
A responsive, dark-themed web interface built with NiceGUI.
```bash
./scripts/run_nicegui.sh
```

**Legacy GUI**
Classic desktop interface (Tkinter).
```bash
./scripts/run_tkinter.sh
```

##  Interface Guide

The Modern UI is divided into a control sidebar and dynamic output panels ("Whisper", "AI", "Translation").

- **Microphone**: Select your input device and monitor audio levels.
- **Model Settings**: Choose Whisper model size (Tiny to Large-v3) and device (CUDA/CPU).
- **AI Processing**: 
  - Enable to use LLMs for proofreading or custom tasks.
  - **Trigger Modes**: "Time" (every X seconds), "Words" (every X words), or "Manual" (Click "Process Now").
  - **Tasks**: Select a persona like "Proofread", "Simplify", or custom ones defined in settings.
- **Text-to-Speech**:
  - **Source**: Speak from Raw Transcript (W), AI Output (A), or Translation (T).
  - **Voice**: Upload a reference file to clone a voice instantly.

##  Configuration

### AI Setup
To use AI features, you need an API key (OpenRouter recommended).
1. Copy the example config: `cp config/.env.example .env`
2. Edit `.env` and add your key: `OPENROUTER_API_KEY=sk-...`

### Custom Personas
Define your own AI assistants in `config/custom_personas.yaml`:
```yaml
summarizer:
  name: "Summarizer"
  prompt: "Summarize the following text into bullet points:"
```

##  File Structure

```
Whispering/
├── config/                 # Configuration files (AI keys, personas)
├── logs/                   # Session logs organized by date
├── scripts/                # Install & Run scripts
├── src/
│   ├── whispering_ui/      # Modern NiceGUI Application
│   │   ├── components/     # UI Widgets (Sidebar, Chat, Help)
│   │   ├── bridge.py       # UI <-> Core Logic Bridge
│   │   └── main.py         # App Entry Point
│   ├── core_parts/         # Audio Device & Signal Processing
│   ├── ai_provider.py      # OpenRouter AI Integration
│   ├── session_logger.py   # JSONL Logging & Recovery System
│   └── tts_controller.py   # TTS & Voice Cloning Logic
├── tts_output/             # Generated Audio Files
└── tts_voices/             # Uploaded Voice Reference Files
```

##  Requirements

### System Requirements
- **OS**: Linux (PipeWire/PulseAudio), Windows 10/11, or macOS.
- **Python**: 3.10 or higher.
- **GPU**: NVIDIA GPU with CUDA 12 recommended for real-time performance.

### Python Dependencies
The core dependencies are installed automatically by `install.sh`, but include:
- `faster-whisper`: Speech recognition engine.
- `nicegui`: Modern web-based UI framework.
- `sounddevice`: Low-level audio input.
- `pywebview` & `PyQt6`: For running as a native desktop window.
- `pyautogui`: For the Auto-Type feature.

##  License

MIT License
