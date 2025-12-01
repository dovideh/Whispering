#!/usr/bin/env python3
"""
Whispering NiceGUI Application
Main entry point for the NiceGUI-based UI
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from nicegui import app, ui
import core
from settings import Settings
from whispering_ui.state import AppState
from whispering_ui.bridge import ProcessingBridge
from whispering_ui.components.sidebar import create_sidebar
from whispering_ui.components.output import create_output_panels


def main():
    """Main application entry point."""

    # === INITIALIZATION ===
    # Load settings
    settings = Settings()

    # Create application state
    state = AppState()

    # Apply loaded settings to state
    state.debug_enabled = settings.get("debug_enabled", False)
    state.text_visible = settings.get("text_visible", False)
    state.model = settings.get("model", "large-v3")
    state.vad_enabled = settings.get("vad", True)
    state.para_detect_enabled = settings.get("para_detect", True)
    state.device = settings.get("device", "cuda")
    state.memory = settings.get("memory", 3)
    state.patience = settings.get("patience", 5.0)
    state.timeout = settings.get("timeout", 5.0)
    state.source_language = settings.get("source_language", "auto")
    state.target_language = settings.get("target_language", "none")

    # Handle autotype setting - convert legacy boolean to string if needed
    autotype_val = settings.get("autotype", "Off")
    if isinstance(autotype_val, bool):
        state.autotype_mode = "Off"  # Convert old boolean format to new string format
    else:
        state.autotype_mode = autotype_val

    state.auto_stop_enabled = settings.get("auto_stop_enabled", False)
    state.auto_stop_minutes = settings.get("auto_stop_minutes", 5)

    # Initialize microphone list
    state.mic_list = core.get_mic_names()

    # Check AI availability
    try:
        from ai_config import load_ai_config
        ai_config = load_ai_config()
        state.ai_available = ai_config is not None

        if state.ai_available:
            # Load AI settings
            state.ai_enabled = settings.get("ai_enabled", False)
            state.ai_persona_index = settings.get("ai_persona_index", 0)
            state.ai_model_index = settings.get("ai_model_index", 0)
            state.ai_translate = settings.get("ai_translate", False)
            state.ai_translate_only = settings.get("ai_translate_only", False)
            state.ai_manual_mode = settings.get("ai_manual_mode", False)
            state.ai_trigger_mode = settings.get("ai_trigger_mode", "time")
            state.ai_process_interval = settings.get("ai_process_interval", 20)
            state.ai_process_words = settings.get("ai_process_words", 150)
    except Exception as e:
        print(f"AI features not available: {e}")
        state.ai_available = False

    # Check TTS availability
    try:
        from tts_controller import TTSController
        state.tts_available = True

        # Load TTS settings
        state.tts_enabled = settings.get("tts_enabled", False)
        state.tts_source = settings.get("tts_source", "whisper")
        state.tts_save_file = settings.get("tts_save_file", False)
    except Exception as e:
        print(f"TTS features not available: {e}")
        state.tts_available = False

    # Create processing bridge
    bridge = ProcessingBridge(state)

    # Initialize TTS controller in bridge if available
    if state.tts_available:
        try:
            from tts_controller import TTSController
            bridge.tts_controller = TTSController(device="auto", output_dir="tts_output")
        except Exception as e:
            print(f"Failed to initialize TTS controller: {e}")
            state.tts_available = False

    # === UI LAYOUT ===
    ui.page_title('Whispering')

    # Create main container - sidebar on left, output on right
    with ui.row().classes('w-full h-screen'):
        # Create output panels first (but will be positioned on right)
        output_container = create_output_panels(state)

        # Sidebar on left - pass output container so it can toggle visibility
        sidebar_container = create_sidebar(state, bridge, output_container)

        # Move sidebar to the left (before output in DOM order)
        sidebar_container.move(output_container)

        # Set initial visibility of output
        if not state.text_visible:
            output_container.set_visibility(False)

    # === SAVE SETTINGS ON EXIT ===
    def save_settings_on_exit():
        """Save settings before application closes."""
        state.is_shutting_down = True

        # Stop recording if active
        if state.is_recording:
            bridge.stop_recording()

        # Save all settings
        settings.set("text_visible", state.text_visible)
        settings.set("debug_enabled", state.debug_enabled)
        settings.set("model", state.model)
        settings.set("vad", state.vad_enabled)
        settings.set("para_detect", state.para_detect_enabled)
        settings.set("device", state.device)
        settings.set("memory", state.memory)
        settings.set("patience", state.patience)
        settings.set("timeout", state.timeout)
        settings.set("source_language", state.source_language)
        settings.set("target_language", state.target_language)
        settings.set("autotype", state.autotype_mode)
        settings.set("auto_stop_enabled", state.auto_stop_enabled)
        settings.set("auto_stop_minutes", state.auto_stop_minutes)

        if state.ai_available:
            settings.set("ai_enabled", state.ai_enabled)
            settings.set("ai_persona_index", state.ai_persona_index)
            settings.set("ai_model_index", state.ai_model_index)
            settings.set("ai_translate", state.ai_translate)
            settings.set("ai_translate_only", state.ai_translate_only)
            settings.set("ai_manual_mode", state.ai_manual_mode)
            settings.set("ai_trigger_mode", state.ai_trigger_mode)
            settings.set("ai_process_interval", state.ai_process_interval)
            settings.set("ai_process_words", state.ai_process_words)

        if state.tts_available:
            settings.set("tts_enabled", state.tts_enabled)
            settings.set("tts_source", state.tts_source)
            settings.set("tts_save_file", state.tts_save_file)

        settings.save()

    # Register cleanup handler
    app.on_shutdown(save_settings_on_exit)

    # === RUN APPLICATION ===
    # Try native mode first, fall back to browser if backend unavailable
    native_mode = False
    try:
        # Check if PyQt6 is available (easiest backend for pywebview)
        import PyQt6
        native_mode = True
        print("\n🚀 Starting Whispering in native window mode...")
    except ImportError:
        print("\n⚠️  PyQt6 not found. Running in browser mode.")
        print("   For native window, install: pip install PyQt6 PyQt6-WebEngine")
        print("   Starting web interface at http://127.0.0.1:8000\n")

    ui.run(
        title='Whispering',
        native=native_mode,
        port=8000,
        window_size=(400 if not state.text_visible else 1200, 800),
        reload=False,
        show=not native_mode  # Only auto-open browser in browser mode
    )


if __name__ == "__main__":
    main()
