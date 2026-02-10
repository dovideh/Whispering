# Whispering NiceGUI UI Module

This directory contains the modular NiceGUI-based user interface for Whispering.

**Note:** This package is named `whispering_ui` (not `ui`) to avoid conflicts with NiceGUI's own `ui` module.

## Architecture

The UI is organized into separate concerns:

### State (`state.py`)
- **Purpose**: Data model holding all application state
- **Key Features**:
  - No UI dependencies (pure Python dataclass)
  - Settings, runtime state, and text buffers
  - Helper methods for text statistics

### Bridge (`bridge.py`)
- **Purpose**: Logic controller connecting state to core processing
- **Key Features**:
  - Manages threading and queues for `core.proc`
  - Polling mechanism using NiceGUI timers
  - AI processor initialization
  - TTS session management
  - Autotype integration

### Components
- **`sidebar.py`**: Control panel with all settings and controls
- **`output.py`**: Text display panels for Whisper, AI, and Translation output

### Main (`main.py`)
- **Purpose**: Entry point that ties everything together
- **Key Features**:
  - Loads settings from disk
  - Initializes state and bridge
  - Builds UI layout
  - Handles cleanup on exit

## Running the Application

To run the NiceGUI version:

```bash
# Use the launcher script
./scripts/run_nicegui.sh

# Or from src directory:
cd src
python -m whispering_ui.main
```

## Design Principles

1. **Separation of Concerns**: State, logic, and UI are completely decoupled
2. **Reactive Updates**: UI updates automatically when state changes
3. **Modern UI**: Material Design-inspired interface via NiceGUI
4. **Web-based**: Can run as desktop app or web server
5. **Easier Testing**: Pure Python state and bridge can be tested independently

## Dependencies

- `nicegui>=1.4.0` - Modern UI framework
- `pyperclip` - Clipboard operations
