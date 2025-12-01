# NiceGUI UI Module

This directory contains the modular NiceGUI-based user interface for Whispering.

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
cd src
python -m ui.main
```

Or from the project root:

```bash
python src/ui/main.py
```

## Key Differences from tkinter Version

1. **Separation of Concerns**: State, logic, and UI are completely decoupled
2. **Reactive Updates**: UI updates automatically when state changes
3. **Modern UI**: Material Design-inspired interface via NiceGUI
4. **Web-based**: Can run as desktop app or web server
5. **Easier Testing**: Pure Python state and bridge can be tested independently

## Dependencies

- `nicegui>=1.4.0` - Modern UI framework
- `pyperclip` - Clipboard operations

## Migration Notes

- The original `gui.py` used tkinter with tight coupling between UI and logic
- This version maintains the same functionality but with clean separation
- The `core.proc` thread interface remains unchanged
- Settings persistence is maintained using the same `Settings` class
