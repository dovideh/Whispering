# Project Structure

This document describes the organization of the Whispering project.

## Directory Layout

```
Whispering/
├── src/                    # Source code
│   ├── core.py            # Core transcription engine
│   ├── tui.py             # Terminal user interface (CLI)
│   ├── whispering_ui/     # NiceGUI application (GUI)
│   │   ├── main.py        # App entry point
│   │   ├── state.py       # Application state model
│   │   ├── bridge.py      # UI <-> Core logic bridge
│   │   └── components/    # UI widgets (sidebar, output, help)
│   ├── ai_config.py       # AI configuration loader
│   ├── ai_provider.py     # AI text processing
│   ├── commands_config.py # Voice commands YAML loader
│   ├── command_detector.py # Voice command pattern matching
│   ├── command_executor.py # Voice command action dispatcher
│   ├── tts_controller.py  # Text-to-speech controller
│   ├── tts_provider.py    # TTS provider interface
│   ├── autotype.py        # Auto-typing functionality
│   ├── settings.py        # Settings persistence
│   ├── cmque.py           # Custom queue implementation
│   ├── session_logger.py  # JSONL session logging & recovery
│   ├── debug_audio.py     # Audio debugging utility
│   └── debug_cuda.py      # CUDA debugging utility
│
├── config/                # Configuration files
│   ├── ai_config.yaml     # AI model configuration
│   ├── custom_personas.yaml # Custom AI assistants
│   ├── voice_commands.yaml # Voice command definitions
│   └── .env.example       # Environment variables template
│
├── scripts/               # Shell scripts
│   ├── install.sh        # Installation script
│   ├── run.sh            # Default launcher (NiceGUI)
│   ├── run_nicegui.sh    # NiceGUI launcher
│   ├── run_nicegui.py    # NiceGUI Python launcher
│   └── debug_env.sh      # Environment debugging
│
├── logs/                 # Session logs organized by date (gitignored)
│
├── requirements.txt      # Python dependencies
├── LICENSE              # Project license
└── .gitignore          # Git ignore rules
```

## Key Components

### Source Code (`src/`)
All Python source files are located in the `src/` directory. The main entry points are:
- `whispering_ui/main.py` - GUI interface (run with `scripts/run.sh`)
- `tui.py` - Terminal interface (run with `python src/tui.py`)

### Configuration (`config/`)
Configuration files that control application behavior:
- `ai_config.yaml` - AI model settings and prompts
- `custom_personas.yaml` - Custom AI assistants
- `voice_commands.yaml` - Voice command definitions
- `.env.example` - Template for environment variables (copy to `.env` in project root)

### Scripts (`scripts/`)
Helper scripts for setup and running the application:
- `install.sh` - Automated installation and setup
- `run.sh` - Launch the GUI with proper environment setup
- `debug_env.sh` - Diagnose CUDA and audio issues

### Logs (`logs/`)
Session logs in JSONL format, organized by date (YY/MM/DD/).

**Note:** This directory is gitignored to keep your transcripts private.

## Installation

### Quick Install
```bash
./scripts/install.sh
```

The install script will:
- Check Python version (3.10+ required)
- Create virtual environment
- Install all dependencies
- Optionally install CUDA libraries
- Create necessary directories
- Set up .env file from template

## Running the Application

### GUI Mode
```bash
./scripts/run.sh
```

### TUI Mode
```bash
# Basic usage
python src/tui.py

# With AI processing
python src/tui.py --ai --ai-persona proofread

# With voice commands and auto-stop
python src/tui.py --voice-commands --auto-stop 10

# See all options
python src/tui.py --help
```

## Development

### Adding Dependencies
```bash
# Activate virtual environment
source .venv/bin/activate

# Install new package
pip install package_name

# Update requirements
pip freeze > requirements.txt
```

### File Organization Rules
- All Python code goes in `src/`
- Configuration files go in `config/`
- Shell scripts go in `scripts/`
- Documentation stays in root (for GitHub visibility)
- User-generated files (logs, settings) are gitignored

## Migration Notes

If you have an existing installation, the file reorganization is backward-compatible:
- `run.sh` now sets `PYTHONPATH` to include `src/`
- Config paths are automatically resolved relative to installation directory
- User settings file (`whispering_settings.json`) remains in project root
