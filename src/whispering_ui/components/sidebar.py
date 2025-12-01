#!/usr/bin/env python3
"""
Complete Sidebar Component
Control panel with all settings and controls
"""

from nicegui import ui
import core
from whispering_ui.state import AppState
from whispering_ui.bridge import ProcessingBridge


def create_sidebar(state: AppState, bridge: ProcessingBridge, output_container=None):
    """
    Create the sidebar control panel with all features.

    Args:
        state: Application state
        bridge: Processing bridge
        output_container: Optional output container for show/hide control
    """

    # Container for all controls
    sidebar_container = ui.column().classes('w-96 p-4 gap-2')

    with sidebar_container:
        # === MICROPHONE SECTION ===
        with ui.row().classes('items-center w-full gap-2'):
            ui.label('Mic:').classes('text-sm w-12')
            mic_display = ["(system default)"] + [name for idx, name in state.mic_list]
            mic_select = ui.select(
                options=mic_display,
                value=mic_display[0] if mic_display else None
            ).classes('flex-grow')
            mic_select.on_value_change(lambda e: setattr(state, 'mic_index',
                                       mic_select.options.index(e.value) if e.value in mic_select.options else 0))

            def refresh_mics():
                bridge.refresh_mics()
                mic_select.options = ["(system default)"] + [name for idx, name in state.mic_list]
                mic_select.update()

            ui.button(icon='refresh', on_click=refresh_mics).props('flat dense').classes('w-10')

        # === TOGGLE TEXT BUTTON ===
        toggle_btn = ui.button(
            'Show Text ▶' if not state.text_visible else 'Hide Text ◀',
            on_click=lambda: _toggle_text(state, toggle_btn, output_container)
        ).classes('w-full mb-2')

        ui.separator().classes('my-2')

        # === MODEL SECTION ===
        ui.label('Model Settings Speech-to-Text').classes('font-bold')

        with ui.row().classes('items-center w-full gap-2'):
            ui.label('Model:').classes('text-sm w-12')
            model_select = ui.select(options=core.models, value=state.model).classes('flex-grow')
            model_select.on_value_change(lambda e: setattr(state, 'model', e.value))

        # Options
        with ui.row().classes('items-center w-full gap-2'):
            vad_cb = ui.checkbox('VAD', value=state.vad_enabled)
            vad_cb.on_value_change(lambda e: setattr(state, 'vad_enabled', e.value))

            para_cb = ui.checkbox('¶', value=state.para_detect_enabled)
            para_cb.on_value_change(lambda e: setattr(state, 'para_detect_enabled', e.value))

            ui.label('Dev:').classes('text-sm')
            dev_select = ui.select(options=core.devices, value=state.device).classes('w-20')
            dev_select.on_value_change(lambda e: setattr(state, 'device', e.value))

        # Autotype
        with ui.row().classes('items-center w-full gap-2'):
            ui.label('⌨ Autotype:').classes('text-sm')
            auto_select = ui.select(
                options=["Off", "Whisper", "Translation", "AI"],
                value=state.autotype_mode
            ).classes('flex-grow')
            auto_select.on_value_change(lambda e: setattr(state, 'autotype_mode', e.value))

        ui.separator().classes('my-2')

        # === TRANSLATION SECTION ===
        ui.label('Translation').classes('font-bold')

        with ui.row().classes('items-center w-full gap-2'):
            ui.label('Source:').classes('text-sm w-16')
            src_select = ui.select(
                options=["auto"] + core.sources,
                value=state.source_language
            ).classes('w-24')
            src_select.on_value_change(lambda e: setattr(state, 'source_language', e.value))

            ui.label('Target:').classes('text-sm w-16')
            tgt_select = ui.select(
                options=["none"] + core.targets,
                value=state.target_language
            ).classes('w-24')
            tgt_select.on_value_change(lambda e: setattr(state, 'target_language', e.value))

        ui.separator().classes('my-2')

        # === AI SECTION ===
        ui.label('AI Processing').classes('font-bold')

        # Enable AI checkbox
        ai_cb = ui.checkbox('Enable AI', value=state.ai_enabled)
        ai_cb.on_value_change(lambda e: setattr(state, 'ai_enabled', e.value))
        if not state.ai_available:
            ai_cb.disable()

        # Task selection (persona)
        task_select = None
        ai_model_combo = None
        if state.ai_available:
            try:
                from ai_config import load_ai_config
                ai_config = load_ai_config()
                if ai_config:
                    # Task (persona) selection
                    personas = ai_config.get_personas()
                    persona_names = [p['name'] for p in personas]

                    with ui.row().classes('items-center w-full gap-2'):
                        ui.label('Task:').classes('text-sm w-12')
                        task_select = ui.select(
                            options=persona_names,
                            value=persona_names[min(state.ai_persona_index, len(persona_names)-1)]
                        ).classes('flex-grow')
                        task_select.on_value_change(lambda e: setattr(state, 'ai_persona_index',
                                                    persona_names.index(e.value) if e.value in persona_names else 0))

                    # Translate output and Translate Only checkboxes
                    with ui.row().classes('items-center w-full gap-2'):
                        ai_trans_cb = ui.checkbox('Translate output', value=state.ai_translate)
                        ai_trans_cb.on_value_change(lambda e: setattr(state, 'ai_translate', e.value))

                        ai_trans_only_cb = ui.checkbox('Translate Only (1:1)', value=state.ai_translate_only)
                        ai_trans_only_cb.on_value_change(lambda e: setattr(state, 'ai_translate_only', e.value))

                    # Model selection
                    models = ai_config.get_models()
                    model_names = [m['name'] for m in models]

                    with ui.row().classes('items-center w-full gap-2'):
                        ui.label('Model:').classes('text-sm w-12')
                        ai_model_combo = ui.select(
                            options=model_names,
                            value=model_names[min(state.ai_model_index, len(model_names)-1)]
                        ).classes('flex-grow')
                        ai_model_combo.on_value_change(lambda e: setattr(state, 'ai_model_index',
                                                       model_names.index(e.value) if e.value in model_names else 0))

                    # Trigger controls - Manual and Automatic side by side
                    with ui.row().classes('items-center w-full gap-2'):
                        # Left side: Manual mode
                        with ui.column().classes('gap-1'):
                            ai_manual_cb = ui.checkbox('Manual mode', value=state.ai_manual_mode)
                            ai_manual_cb.on_value_change(lambda e: _on_manual_mode_changed(state, e.value, ai_process_btn, ai_trigger_select, ai_interval_select, ai_words_num))

                            ai_process_btn = ui.button('⚡ Process Now', on_click=lambda: bridge.manual_ai_trigger()).classes('w-32')
                            ai_process_btn.set_enabled(state.ai_manual_mode)

                        # Right side: Automatic triggers
                        with ui.column().classes('gap-1 flex-grow'):
                            with ui.row().classes('items-center gap-2'):
                                ui.label('Trigger:').classes('text-sm')
                                ai_trigger_select = ui.select(
                                    options=["Time", "Words"],
                                    value=state.ai_trigger_mode.capitalize()
                                ).classes('w-20')
                                ai_trigger_select.on_value_change(lambda e: _on_trigger_changed(state, e.value, ai_interval_select, ai_words_num))
                                ai_trigger_select.set_enabled(not state.ai_manual_mode)

                            # Interval/Words control (shows one at a time)
                            with ui.row().classes('items-center gap-2'):
                                interval_labels = ["5s", "10s", "15s", "20s", "25s", "30s", "45s", "1m", "1.5m", "2m"]
                                interval_values = [5, 10, 15, 20, 25, 30, 45, 60, 90, 120]
                                interval_map = dict(zip(interval_labels, interval_values))

                                # Find current label
                                current_label = "20s"
                                for lbl, val in interval_map.items():
                                    if val == state.ai_process_interval:
                                        current_label = lbl
                                        break

                                ui.label('Interval:').classes('text-sm')
                                ai_interval_select = ui.select(
                                    options=interval_labels,
                                    value=current_label
                                ).classes('w-16')
                                def on_interval_change(e):
                                    state.ai_process_interval = interval_map.get(e.value, 20)
                                ai_interval_select.on_value_change(on_interval_change)
                                ai_interval_select.set_enabled(not state.ai_manual_mode)
                                ai_interval_select.set_visibility(state.ai_trigger_mode == "time")

                                ui.label('words:').classes('text-sm')
                                ai_words_num = ui.number(value=state.ai_process_words, min=50, max=500, step=50, format='%.0f').classes('w-20')
                                ai_words_num.on_value_change(lambda e: setattr(state, 'ai_process_words', int(e.value or 150)))
                                ai_words_num.set_enabled(not state.ai_manual_mode)
                                ai_words_num.set_visibility(state.ai_trigger_mode == "words")

            except Exception as e:
                print(f"Error loading AI config: {e}")
        else:
            # AI not available - show disabled controls
            ai_trans_cb = ui.checkbox('Translate output', value=False)
            ai_trans_cb.disable()

        ui.separator().classes('my-2')

        # === TTS SECTION ===
        ui.label('Text-to-Speech').classes('font-bold')

        # Enable TTS checkbox
        tts_cb = ui.checkbox('Enable TTS', value=state.tts_enabled)
        tts_cb.on_value_change(lambda e: setattr(state, 'tts_enabled', e.value))
        if not state.tts_available:
            tts_cb.disable()

        if state.tts_available:
            # Source selection (W/A/T mutually exclusive checkboxes)
            with ui.row().classes('items-center w-full gap-2'):
                ui.label('Source:').classes('text-sm')

                tts_w_cb = ui.checkbox('W', value=(state.tts_source == "whisper"))
                tts_w_cb.on_value_change(lambda e: _on_tts_source_changed(state, "whisper", e.value, tts_w_cb, tts_a_cb, tts_t_cb))

                tts_a_cb = ui.checkbox('A', value=(state.tts_source == "ai"))
                tts_a_cb.on_value_change(lambda e: _on_tts_source_changed(state, "ai", e.value, tts_w_cb, tts_a_cb, tts_t_cb))

                tts_t_cb = ui.checkbox('T', value=(state.tts_source == "translation"))
                tts_t_cb.on_value_change(lambda e: _on_tts_source_changed(state, "translation", e.value, tts_w_cb, tts_a_cb, tts_t_cb))

            # Voice selection
            with ui.row().classes('items-center w-full gap-2'):
                ui.label('Voice:').classes('text-sm')
                tts_voice_label = ui.label(state.tts_voice_display_name).classes('flex-grow text-gray-600')

                tts_browse_btn = ui.button('Browse', on_click=lambda: _browse_voice(state, bridge, tts_voice_label)).classes('text-xs')
                tts_clear_btn = ui.button('Clear', on_click=lambda: _clear_voice(state, bridge, tts_voice_label)).classes('text-xs')

            # Output options
            with ui.row().classes('items-center w-full gap-2'):
                ui.label('Output:').classes('text-sm')
                tts_save_cb = ui.checkbox('Save to file', value=state.tts_save_file)
                tts_save_cb.on_value_change(lambda e: setattr(state, 'tts_save_file', e.value))

                tts_format_select = ui.select(options=["wav", "ogg"], value=state.tts_format).classes('w-20')
                tts_format_select.on_value_change(lambda e: setattr(state, 'tts_format', e.value))

            # TTS status
            tts_status_label = ui.label('').classes('text-xs text-blue-600')

            # Update TTS status periodically
            def update_tts_status():
                if state.tts_status_message:
                    tts_status_label.text = state.tts_status_message
                else:
                    tts_status_label.text = ''

            ui.timer(0.2, update_tts_status)

        ui.separator().classes('my-2')

        # === CONTROL SECTION ===
        control_btn = ui.button(
            'Start',
            on_click=lambda: _toggle_recording(state, bridge, control_btn, level_progress, status_label)
        ).classes('w-full').props('color=primary')

        # Audio level
        with ui.row().classes('items-center w-full gap-2'):
            ui.label('Level:').classes('text-sm w-12')
            level_progress = ui.linear_progress(value=0, show_value=False).classes('flex-grow')

        # Auto-stop
        with ui.row().classes('items-center w-full gap-2'):
            autostop_cb = ui.checkbox('Auto-stop after', value=state.auto_stop_enabled)
            autostop_cb.on_value_change(lambda e: setattr(state, 'auto_stop_enabled', e.value))

            autostop_num = ui.number(value=state.auto_stop_minutes, min=1, max=60, step=1,
                                     format='%.0f').classes('w-16')
            autostop_num.on_value_change(lambda e: setattr(state, 'auto_stop_minutes', int(e.value or 5)))

            ui.label('min').classes('text-sm')

        # Status
        status_label = ui.label('').classes('text-sm text-red-600 mt-2')

        # Update UI periodically
        def update_ui():
            # Update button
            if state.is_recording:
                control_btn.text = 'Stop'
                control_btn.props('color=negative')
            else:
                control_btn.text = 'Start'
                control_btn.props('color=primary')

            # Update level - NO smoothing, direct value
            level_progress.value = state.audio_level / 100.0

            # Update status
            if state.error_message:
                status_label.text = f'Error: {state.error_message}'
            elif state.status_message:
                status_label.text = state.status_message
            else:
                status_label.text = ''

        ui.timer(0.05, update_ui)  # Faster update for audio level (50ms instead of 100ms)

    return sidebar_container


def _toggle_text(state: AppState, btn, output_container):
    """Toggle text visibility."""
    state.text_visible = not state.text_visible
    btn.text = 'Hide Text ◀' if state.text_visible else 'Show Text ▶'

    # Show/hide the output container
    if output_container:
        output_container.set_visibility(state.text_visible)

    ui.notify(f'Text panels {"shown" if state.text_visible else "hidden"}')


def _toggle_recording(state: AppState, bridge: ProcessingBridge, btn, level, status):
    """Toggle recording on/off."""
    if state.is_recording:
        bridge.stop_recording()
    else:
        bridge.start_recording()


def _on_manual_mode_changed(state: AppState, manual_mode: bool, process_btn, trigger_select, interval_select, words_num):
    """Handle manual mode checkbox change."""
    state.ai_manual_mode = manual_mode

    # Enable/disable controls
    process_btn.set_enabled(manual_mode)
    trigger_select.set_enabled(not manual_mode)
    interval_select.set_enabled(not manual_mode and state.ai_trigger_mode == "time")
    words_num.set_enabled(not manual_mode and state.ai_trigger_mode == "words")


def _on_trigger_changed(state: AppState, trigger_mode: str, interval_select, words_num):
    """Handle trigger mode change."""
    state.ai_trigger_mode = trigger_mode.lower()

    # Show/hide appropriate control
    if trigger_mode == "Time":
        interval_select.set_visibility(True)
        words_num.set_visibility(False)
    else:  # Words
        interval_select.set_visibility(False)
        words_num.set_visibility(True)


def _on_tts_source_changed(state: AppState, source: str, checked: bool, w_cb, a_cb, t_cb):
    """Handle TTS source selection (mutually exclusive)."""
    if not checked:
        # Don't allow unchecking - must have one selected
        return

    state.tts_source = source

    # Update checkboxes to be mutually exclusive
    w_cb.value = (source == "whisper")
    a_cb.value = (source == "ai")
    t_cb.value = (source == "translation")


def _browse_voice(state: AppState, bridge: ProcessingBridge, voice_label):
    """Browse for voice reference file."""
    # For now, just show a message - file dialog requires additional implementation
    ui.notify("Voice browsing not yet implemented in web UI")
    # TODO: Implement file upload for voice reference


def _clear_voice(state: AppState, bridge: ProcessingBridge, voice_label):
    """Clear voice reference."""
    state.tts_voice_reference = None
    state.tts_voice_display_name = "Default"
    voice_label.text = "Default"

    if bridge.tts_controller:
        bridge.tts_controller.set_reference_voice(None)

    ui.notify("Voice cleared - using default")
