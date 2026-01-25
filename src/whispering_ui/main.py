#!/usr/bin/env python3
"""
Whispering NiceGUI Application
Main entry point for the NiceGUI-based UI
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from nicegui import app, ui
import core
from settings import Settings
from whispering_ui.state import AppState
from whispering_ui.bridge import ProcessingBridge
from whispering_ui.components.sidebar import create_sidebar, sync_text_layout
from whispering_ui.components.output import create_output_panels
from debug import set_debug_enabled
from session_logger import SessionLogger


def main():
    """Main application entry point."""

    # === INITIALIZATION ===
    # Load settings
    settings = Settings()

    # Create application state
    state = AppState()

    # Apply loaded settings to state
    state.debug_enabled = settings.get("debug_enabled", False)
    set_debug_enabled(state.debug_enabled)
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

    # Initialize microphone and monitor lists
    try:
        state.mic_list = core.get_mic_names()
    except Exception as e:
        print(f"Error getting mic list: {e}")
        state.mic_list = []

    try:
        state.monitor_list = core.get_monitor_names()
    except Exception as e:
        print(f"Error getting monitor list: {e}")
        state.monitor_list = []

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
        state.tts_format = settings.get("tts_format", "wav")
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

    # === RECOVERY DIALOG ===
    # Check for crashed sessions and offer recovery
    def check_crashed_sessions():
        """Check for crashed sessions and show recovery dialog."""
        try:
            from session_logger import SessionLogger
            logger = SessionLogger()
            temp_files = logger.scan_for_temp_files()
            
            if temp_files:
                # Show recovery dialog for each crashed session
                for temp_file, timestamp in temp_files:
                    with ui.dialog() as dialog, ui.card().classes('w-96'):
                        ui.label(f'Found incomplete session from {timestamp}').classes('text-lg font-bold mb-4')
                        ui.label('Would you like to recover this session or discard it?').classes('mb-4')
                        
                        with ui.row().classes('justify-center gap-4 mt-4'):
                            ui.button('Recover', on_click=lambda: recover_session(temp_file, logger, dialog)).props('color=primary')
                            ui.button('Discard', on_click=lambda: discard_session(temp_file, logger, dialog)).props('color=negative')
                        
                        ui.label('Note: Recovery will save the session to logs.').classes('text-xs text-gray-500 mt-2')
                    
                    dialog.open()
        except Exception as e:
            print(f"Error checking crashed sessions: {e}")

    def recover_session(temp_file, logger, dialog):
        """Recover a crashed session and load text into UI."""
        try:
            # First, load the outputs from the temp file before renaming
            outputs = logger.load_session_outputs(temp_file)

            # Now recover (rename) the session
            final_file = logger.recover_session(temp_file)
            if final_file:
                # Load recovered text into UI state
                if outputs:
                    state.whisper_text = outputs.get("whisper_text", "")
                    state.ai_text = outputs.get("ai_text", "")
                    state.translation_text = outputs.get("translation_text", "")
                    ui.notify('✓ Session recovered and text restored', type='positive')
                    print(f"Recovered session with text: {final_file}")
                else:
                    ui.notify('✓ Session recovered (no text content)', type='positive')
                    print(f"Recovered session (empty): {final_file}")
            else:
                ui.notify('✗ Failed to recover session', type='negative')
        except Exception as e:
            ui.notify(f'✗ Recovery error: {e}', type='negative')
            print(f"Recovery error: {e}")
        finally:
            dialog.close()

    def discard_session(temp_file, logger, dialog):
        """Discard a crashed session."""
        try:
            success = logger.discard_session(temp_file)
            if success:
                ui.notify('✓ Session discarded', type='positive')
                print(f"Discarded session: {temp_file}")
            else:
                ui.notify('✗ Failed to discard session', type='negative')
        except Exception as e:
            ui.notify(f'✗ Discard error: {e}', type='negative')
            print(f"Discard error: {e}")
        finally:
            dialog.close()

    # === UI SETUP ===
    ui.page_title('Whispering')

    # Enable dark mode
    ui.dark_mode().enable()

    # Add custom CSS for compact, modern dark theme
    ui.add_head_html('''
        <style>
            /* Compact spacing */
            .q-page {
                padding: 0 !important;
            }

            .workspace-row {
                transition: max-width 0.25s ease;
            }

            .workspace-row.workspace-collapsed {
                max-width: 420px;
                margin: 0 auto;
            }

            /* Sidebar - fixed width, dark background */
            .sidebar-container {
                background: #1e1e1e;
                border-right: 1px solid #333;
                overflow-y: auto;
                min-width: 350px !important;
                max-width: 350px !important;
            }

            /* Output panels - take remaining space */
            .output-container {
                background: #121212;
                flex: 1;
                display: flex;
                flex-direction: column;
                min-height: 0;
                height: 100%;
                overflow: hidden;
                padding: 0;
            }

            .output-stack {
                display: flex;
                flex-direction: column;
                gap: 0.35rem;
                flex: 1;
                min-height: 0;
                height: 100%;
                width: 100%;
                padding: 0.4rem 0.5rem 0.4rem 0.4rem;
            }

            .output-panel {
                background: #181818;
                border: 1px solid #2a2a2a;
                border-radius: 8px;
                padding: 0.35rem 0.55rem 0.3rem;
                display: flex;
                flex-direction: column;
                min-height: 0;
                flex: 1 1 0;
                width: 100%;
            }

            .output-panel .panel-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 0.05rem;
            }

            .output-panel .q-field {
                flex: 1 1 0;
                display: flex;
                flex-direction: column;
                min-height: 0;
                margin: 0;
                --q-field-padding: 0;
                --q-field-label-padding: 0;
            }

            .output-panel .q-field__inner,
            .output-panel .q-field__control,
            .output-panel .q-field__native {
                flex: 1 1 0;
                min-height: 0;
                height: 100%;
                width: 100%;
            }

            .output-panel .q-field__bottom,
            .output-panel .q-field__messages {
                display: none;
            }

            .output-panel .q-field__control {
                align-items: stretch;
            }

            .output-panel .q-field__native textarea {
                height: 100% !important;
                min-height: 0;
                width: 100%;
                resize: none;
                padding: 0;
                margin: 0;
            }

            .output-textarea {
                flex: 1 1 0;
                min-height: 0;
                width: 100%;
                height: 100%;
                resize: none;
                font-family: Menlo, Consolas, 'Liberation Mono', monospace;
                padding-bottom: 0;
                margin: 0;
            }

            .section-muted {
                opacity: 0.65;
            }

            /* Compact controls */
            .q-field__control {
                min-height: 32px !important;
            }

            .q-btn {
                font-size: 0.875rem !important;
            }

            /* Section separators */
            .q-separator {
                background: #333 !important;
            }

            /* Scrollbars */
            ::-webkit-scrollbar {
                width: 8px;
            }

            ::-webkit-scrollbar-track {
                background: #1e1e1e;
            }

            ::-webkit-scrollbar-thumb {
                background: #444;
                border-radius: 4px;
            }
        </style>
    ''')

    # === UI LAYOUT ===
    # Horizontal split: sidebar (left) | output panels (right)
    with ui.row().classes('workspace-row w-full h-screen').style('margin: 0; padding: 0; gap: 0;') as workspace_row:
        # Sidebar on left - fixed width
        sidebar_container = create_sidebar(state, bridge, None).classes('sidebar-container')

        # Output panels on right - flex grow (pass bridge for audio controls)
        output_container = create_output_panels(state, bridge).classes('output-container')

        # Connect sidebar to output for show/hide
        sidebar_container._output_container = output_container
        sidebar_container._layout_row = workspace_row

        # Set initial visibility
        sync_text_layout(state, sidebar_container, notify=False)

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
            settings.set("tts_format", state.tts_format)

        settings.save()

    # Register cleanup handler
    app.on_shutdown(save_settings_on_exit)

    # === CHECK FOR CRASHED SESSIONS ===
    # Check for crashed sessions before UI setup
    check_crashed_sessions()

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

    if native_mode:
        os.environ.setdefault('PYWEBVIEW_GUI', 'qt')

    def launch_ui(use_native: bool):
        ui.run(
            title='Whispering',
            native=use_native,
            port=8000,
            window_size=(400 if not state.text_visible else 1200, 1000),
            reload=False,
            show=not use_native  # Only auto-open browser in browser mode
        )

    try:
        launch_ui(native_mode)
    except ModuleNotFoundError as exc:
        if native_mode and exc.name == 'gi':
            print("\n⚠️  GTK bindings (gi) are missing; falling back to browser mode.\n")
            launch_ui(False)
        else:
            raise


if __name__ == "__main__":
    main()
