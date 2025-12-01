#!/usr/bin/env python3
"""
Complete Sidebar Component with Help and File Upload
Control panel with all settings and controls
"""

from nicegui import ui, app
import core
from whispering_ui.state import AppState
from whispering_ui.bridge import ProcessingBridge
from whispering_ui.components.help import show_help_dialog
from pathlib import Path


def create_sidebar(state: AppState, bridge: ProcessingBridge, output_container=None):
    """
    Create the sidebar control panel with all features.

    Args:
        state: Application state
        bridge: Processing bridge
        output_container: Optional output container for show/hide control
    """

    # Container for all controls - compact spacing
    sidebar_container = ui.column().classes('w-full h-full p-3 gap-1').style('overflow-y: auto;')

    with sidebar_container:
        # === MICROPHONE SECTION ===
        with ui.row().classes('items-center w-full gap-1'):
            ui.label('Mic:').classes('text-xs w-10')
            mic_display = ["(system default)"] + [name for idx, name in state.mic_list]
            mic_select = ui.select(
                options=mic_display,
                value=mic_display[0] if mic_display else None
            ).classes('flex-grow').props('dense')
            mic_select.on_value_change(lambda e: setattr(state, 'mic_index',
                                       mic_select.options.index(e.value) if e.value in mic_select.options else 0))

            def refresh_mics():
                bridge.refresh_mics()
                mic_select.options = ["(system default)"] + [name for idx, name in state.mic_list]
                mic_select.update()

            ui.button(icon='refresh', on_click=refresh_mics).props('flat dense round size=sm')

        # === TOGGLE TEXT BUTTON ===
        toggle_btn = ui.button(
            'Show Text ▶' if not state.text_visible else 'Hide Text ◀',
            on_click=lambda: _toggle_text(state, toggle_btn, sidebar_container)
        ).classes('w-full').props('dense')

        ui.separator().classes('my-1')

        # === MODEL SECTION ===
        with ui.row().classes('items-center justify-between w-full'):
            ui.label('Model Settings STT').classes('font-bold text-sm')
            ui.button(icon='help_outline', on_click=lambda: show_help_dialog('model')).props('flat dense round size=sm')

        with ui.row().classes('items-center w-full gap-1'):
            ui.label('Model:').classes('text-xs w-12')
            model_select = ui.select(options=core.models, value=state.model).classes('flex-grow').props('dense')
            model_select.on_value_change(lambda e: setattr(state, 'model', e.value))

        # Options row - compact
        with ui.row().classes('items-center w-full gap-2'):
            vad_cb = ui.checkbox('VAD', value=state.vad_enabled).props('dense')
            vad_cb.on_value_change(lambda e: setattr(state, 'vad_enabled', e.value))

            para_cb = ui.checkbox('¶', value=state.para_detect_enabled).props('dense')
            para_cb.on_value_change(lambda e: setattr(state, 'para_detect_enabled', e.value))

            ui.label('Dev:').classes('text-xs')
            dev_select = ui.select(options=core.devices, value=state.device).classes('w-16').props('dense')
            dev_select.on_value_change(lambda e: setattr(state, 'device', e.value))

        # Autotype
        with ui.row().classes('items-center w-full gap-1'):
            ui.label('⌨:').classes('text-xs w-8')
            auto_select = ui.select(
                options=["Off", "Whisper", "Translation", "AI"],
                value=state.autotype_mode
            ).classes('flex-grow').props('dense')
            auto_select.on_value_change(lambda e: setattr(state, 'autotype_mode', e.value))

        ui.separator().classes('my-1')

        # === TRANSLATION SECTION ===
        with ui.row().classes('items-center justify-between w-full'):
            ui.label('Translation').classes('font-bold text-sm')
            ui.button(icon='help_outline', on_click=lambda: show_help_dialog('translate')).props('flat dense round size=sm')

        with ui.row().classes('items-center w-full gap-1'):
            ui.label('Src:').classes('text-xs w-8')
            src_select = ui.select(
                options=["auto"] + core.sources,
                value=state.source_language
            ).classes('w-20').props('dense')
            src_select.on_value_change(lambda e: setattr(state, 'source_language', e.value))

            ui.label('Tgt:').classes('text-xs w-8')
            tgt_select = ui.select(
                options=["none"] + core.targets,
                value=state.target_language
            ).classes('w-20').props('dense')
            tgt_select.on_value_change(lambda e: setattr(state, 'target_language', e.value))

        ui.separator().classes('my-1')

        # === AI SECTION ===
        with ui.row().classes('items-center justify-between w-full'):
            ui.label('AI Processing').classes('font-bold text-sm')
            if state.ai_available:
                ui.button(icon='help_outline', on_click=lambda: show_help_dialog('ai')).props('flat dense round size=sm')

        # Enable AI checkbox
        ai_cb = ui.checkbox('Enable AI', value=state.ai_enabled).props('dense')
        ai_section = ui.column().classes('w-full gap-1')

        def on_ai_toggle(e):
            state.ai_enabled = e.value
            _set_section_visual_state(ai_section, e.value)

        ai_cb.on_value_change(on_ai_toggle)
        if not state.ai_available:
            ai_cb.disable()

        # AI controls
        if state.ai_available:
            with ai_section:
                try:
                    from ai_config import load_ai_config
                    ai_config = load_ai_config()
                    if ai_config:
                        # Task selection
                        personas = ai_config.get_personas()
                        persona_names = [p['name'] for p in personas]

                        with ui.row().classes('items-center w-full gap-1'):
                            ui.label('Task:').classes('text-xs w-12')
                            task_select = ui.select(
                                options=persona_names,
                                value=persona_names[min(state.ai_persona_index, len(persona_names)-1)]
                            ).classes('flex-grow').props('dense')
                            task_select.on_value_change(lambda e: setattr(state, 'ai_persona_index',
                                                        persona_names.index(e.value) if e.value in persona_names else 0))

                        # Translate checkboxes - compact
                        with ui.row().classes('items-center w-full gap-2'):
                            ai_trans_cb = ui.checkbox('Translate', value=state.ai_translate).props('dense')
                            ai_trans_cb.on_value_change(lambda e: setattr(state, 'ai_translate', e.value))

                            ai_trans_only_cb = ui.checkbox('Only (1:1)', value=state.ai_translate_only).props('dense')
                            ai_trans_only_cb.on_value_change(lambda e: setattr(state, 'ai_translate_only', e.value))

                        # Model selection
                        models = ai_config.get_models()
                        model_names = [m['name'] for m in models]

                        with ui.row().classes('items-center w-full gap-1'):
                            ui.label('Model:').classes('text-xs w-12')
                            ai_model_combo = ui.select(
                                options=model_names,
                                value=model_names[min(state.ai_model_index, len(model_names)-1)]
                            ).classes('flex-grow').props('dense')
                            ai_model_combo.on_value_change(lambda e: setattr(state, 'ai_model_index',
                                                           model_names.index(e.value) if e.value in model_names else 0))

                        # Trigger controls - compact layout
                        ai_manual_cb = ui.checkbox('Manual mode', value=state.ai_manual_mode).props('dense')

                        ai_process_btn = ui.button('⚡ Process Now', on_click=lambda: bridge.manual_ai_trigger()).classes('w-full').props('dense')
                        ai_process_btn.set_enabled(state.ai_manual_mode)

                        # Trigger mode and settings
                        with ui.row().classes('items-center w-full gap-1'):
                            ui.label('Trigger:').classes('text-xs')
                            ai_trigger_select = ui.select(
                                options=["Time", "Words"],
                                value=state.ai_trigger_mode.capitalize()
                            ).classes('w-16').props('dense')
                            ai_trigger_select.set_enabled(not state.ai_manual_mode)

                            # Interval control
                            interval_labels = ["5s", "10s", "15s", "20s", "25s", "30s", "45s", "1m", "1.5m", "2m"]
                            interval_values = [5, 10, 15, 20, 25, 30, 45, 60, 90, 120]
                            interval_map = dict(zip(interval_labels, interval_values))

                            current_label = "20s"
                            for lbl, val in interval_map.items():
                                if val == state.ai_process_interval:
                                    current_label = lbl
                                    break

                            ui.label('Int:').classes('text-xs')
                            ai_interval_select = ui.select(
                                options=interval_labels,
                                value=current_label
                            ).classes('w-14').props('dense')

                            def on_interval_change(e):
                                state.ai_process_interval = interval_map.get(e.value, 20)

                            ai_interval_select.on_value_change(on_interval_change)
                            ai_interval_select.set_enabled(not state.ai_manual_mode)
                            ai_interval_select.set_visibility(state.ai_trigger_mode == "time")

                            ui.label('W:').classes('text-xs')
                            ai_words_num = ui.number(value=state.ai_process_words, min=50, max=500, step=50).classes('w-16').props('dense')
                            ai_words_num.on_value_change(lambda e: setattr(state, 'ai_process_words', int(e.value or 150)))
                            ai_words_num.set_enabled(not state.ai_manual_mode)
                            ai_words_num.set_visibility(state.ai_trigger_mode == "words")

                        # Wire up event handlers
                        ai_manual_cb.on_value_change(lambda e: _on_manual_mode_changed(
                            state, e.value, ai_process_btn, ai_trigger_select, ai_interval_select, ai_words_num))

                        ai_trigger_select.on_value_change(lambda e: _on_trigger_changed(
                            state, e.value, ai_interval_select, ai_words_num))

                except Exception as e:
                    print(f"Error loading AI config: {e}")

        _set_section_visual_state(ai_section, state.ai_enabled and state.ai_available)

        ui.separator().classes('my-1')

        # === TTS SECTION ===
        with ui.row().classes('items-center justify-between w-full'):
            ui.label('Text-to-Speech').classes('font-bold text-sm')
            if state.tts_available:
                ui.button(icon='help_outline', on_click=lambda: show_help_dialog('tts')).props('flat dense round size=sm')

        # Enable TTS
        tts_cb = ui.checkbox('Enable TTS', value=state.tts_enabled).props('dense')
        tts_section = ui.column().classes('w-full gap-1')

        def on_tts_toggle(e):
            state.tts_enabled = e.value
            _set_section_visual_state(tts_section, e.value)

        tts_cb.on_value_change(on_tts_toggle)
        if not state.tts_available:
            tts_cb.disable()

        if state.tts_available:
            with tts_section:
                # Source selection - compact
                with ui.row().classes('items-center w-full gap-1'):
                    ui.label('Src:').classes('text-xs w-10')

                    tts_w_cb = ui.checkbox('W', value=(state.tts_source == "whisper")).props('dense')
                    tts_a_cb = ui.checkbox('A', value=(state.tts_source == "ai")).props('dense')
                    tts_t_cb = ui.checkbox('T', value=(state.tts_source == "translation")).props('dense')

                    tts_w_cb.on_value_change(lambda e: _on_tts_source_changed(state, "whisper", e.value, tts_w_cb, tts_a_cb, tts_t_cb))
                    tts_a_cb.on_value_change(lambda e: _on_tts_source_changed(state, "ai", e.value, tts_w_cb, tts_a_cb, tts_t_cb))
                    tts_t_cb.on_value_change(lambda e: _on_tts_source_changed(state, "translation", e.value, tts_w_cb, tts_a_cb, tts_t_cb))

                # Voice selection with streamlined upload
                with ui.row().classes('items-center w-full gap-1'):
                    ui.label('Voice:').classes('text-xs w-10')
                    tts_voice_label = ui.label(state.tts_voice_display_name).classes('flex-grow text-xs text-gray-400 truncate')

                    upload = ui.upload(
                        on_upload=lambda e: _on_voice_upload(e, state, bridge, tts_voice_label),
                        auto_upload=True,
                        max_file_size=50_000_000,
                        max_files=1
                    ).props('accept=audio/*').classes('hidden')

                    ui.button(icon='folder_open', on_click=lambda u=upload: u.run_method('pickFiles')).props('flat dense round size=sm')
                    ui.button(icon='clear', on_click=lambda: _clear_voice(state, bridge, tts_voice_label)).props('flat dense round size=sm')

                # Output options - compact
                with ui.row().classes('items-center w-full gap-1'):
                    ui.label('Out:').classes('text-xs w-10')
                    tts_save_cb = ui.checkbox('Save', value=state.tts_save_file).props('dense')
                    tts_save_cb.on_value_change(lambda e: setattr(state, 'tts_save_file', e.value))

                    tts_format_select = ui.select(options=["wav", "ogg"], value=state.tts_format).classes('w-16').props('dense')
                    tts_format_select.on_value_change(lambda e: setattr(state, 'tts_format', e.value))

                # TTS status - compact
                tts_status_label = ui.label('').classes('text-xs text-blue-400')

                def update_tts_status():
                    if state.tts_status_message:
                        tts_status_label.text = state.tts_status_message[:50]
                    else:
                        tts_status_label.text = ''

                ui.timer(0.2, update_tts_status)

        _set_section_visual_state(tts_section, state.tts_enabled and state.tts_available)

        ui.separator().classes('my-1')

        # === CONTROL SECTION ===
        control_btn = ui.button(
            'Start',
            on_click=lambda: _toggle_recording(state, bridge, control_btn, level_progress, status_label)
        ).classes('w-full').props('color=primary')

        # Audio level - compact
        with ui.row().classes('items-center w-full gap-1'):
            ui.label('Level:').classes('text-xs w-12')
            level_progress = ui.linear_progress(value=0, show_value=False).classes('flex-grow')

        # Auto-stop - compact
        with ui.row().classes('items-center w-full gap-1'):
            autostop_cb = ui.checkbox('Auto-stop', value=state.auto_stop_enabled).props('dense')
            autostop_cb.on_value_change(lambda e: setattr(state, 'auto_stop_enabled', e.value))

            autostop_num = ui.number(value=state.auto_stop_minutes, min=1, max=60, step=1).classes('w-14').props('dense')
            autostop_num.on_value_change(lambda e: setattr(state, 'auto_stop_minutes', int(e.value or 5)))

            ui.label('min').classes('text-xs')

        # Status - compact
        status_label = ui.label('').classes('text-xs text-red-400 mt-1')

        # Update UI periodically - faster for audio level
        def update_ui():
            # Update button
            if state.is_recording:
                control_btn.text = 'Stop'
                control_btn.props('color=negative')
            else:
                control_btn.text = 'Start'
                control_btn.props('color=primary')

            # Update level - NO smoothing
            level_progress.value = state.audio_level / 100.0

            # Update status
            if state.error_message:
                status_label.text = f'Error: {state.error_message[:40]}'
            elif state.status_message:
                status_label.text = state.status_message[:40]
            else:
                status_label.text = ''

        ui.timer(0.05, update_ui)

    return sidebar_container


def _toggle_text(state: AppState, btn, sidebar_container):
    """Toggle text visibility."""
    state.text_visible = not state.text_visible
    btn.text = 'Hide Text ◀' if state.text_visible else 'Show Text ▶'

    sync_text_layout(state, sidebar_container, notify=True)


def _toggle_recording(state: AppState, bridge: ProcessingBridge, btn, level, status):
    """Toggle recording on/off."""
    if state.is_recording:
        bridge.stop_recording()
    else:
        bridge.start_recording()


def _on_manual_mode_changed(state: AppState, manual_mode: bool, process_btn, trigger_select, interval_select, words_num):
    """Handle manual mode checkbox change."""
    state.ai_manual_mode = manual_mode
    process_btn.set_enabled(manual_mode)
    trigger_select.set_enabled(not manual_mode)
    interval_select.set_enabled(not manual_mode and state.ai_trigger_mode == "time")
    words_num.set_enabled(not manual_mode and state.ai_trigger_mode == "words")


def _on_trigger_changed(state: AppState, trigger_mode: str, interval_select, words_num):
    """Handle trigger mode change."""
    state.ai_trigger_mode = trigger_mode.lower()

    if trigger_mode == "Time":
        interval_select.set_visibility(True)
        words_num.set_visibility(False)
    else:  # Words
        interval_select.set_visibility(False)
        words_num.set_visibility(True)


def _on_tts_source_changed(state: AppState, source: str, checked: bool, w_cb, a_cb, t_cb):
    """Handle TTS source selection (mutually exclusive)."""
    if not checked:
        return

    state.tts_source = source
    w_cb.value = (source == "whisper")
    a_cb.value = (source == "ai")
    t_cb.value = (source == "translation")


def _on_voice_upload(event, state: AppState, bridge: ProcessingBridge, voice_label):
    """Handle voice file upload."""
    try:
        # Get uploaded file
        file_path = event.name
        filename = Path(file_path).name

        # Set voice reference
        state.tts_voice_reference = file_path
        state.tts_voice_display_name = filename[:20] + "..." if len(filename) > 20 else filename
        voice_label.text = state.tts_voice_display_name

        if bridge.tts_controller:
            # The file is saved by NiceGUI in a temporary location
            # We need to use the actual uploaded content
            with open(event.name, 'rb') as f:
                content = f.read()

            # Save to permanent location
            tts_voice_dir = Path("tts_voices")
            tts_voice_dir.mkdir(exist_ok=True)
            permanent_path = tts_voice_dir / filename

            with open(permanent_path, 'wb') as f:
                f.write(content)

            bridge.tts_controller.set_reference_voice(str(permanent_path))
            state.tts_voice_reference = str(permanent_path)

        ui.notify(f"Voice loaded: {filename}", type='positive')
    except Exception as e:
        ui.notify(f"Error loading voice: {e}", type='negative')
        print(f"Voice upload error: {e}")


def _clear_voice(state: AppState, bridge: ProcessingBridge, voice_label):
    """Clear voice reference."""
    state.tts_voice_reference = None
    state.tts_voice_display_name = "Default"
    voice_label.text = "Default"

    if bridge.tts_controller:
        bridge.tts_controller.set_reference_voice(None)

    ui.notify("Voice cleared - using default")


def sync_text_layout(state: AppState, sidebar_container, *, notify: bool = False):
    """Apply sidebar/output layout updates when text panes toggle."""
    output_container = getattr(sidebar_container, '_output_container', None)
    if output_container:
        output_container.set_visibility(state.text_visible)

    layout_row = getattr(sidebar_container, '_layout_row', None)
    if layout_row:
        if state.text_visible:
            layout_row.classes(remove='workspace-collapsed')
        else:
            layout_row.classes(add='workspace-collapsed')

    _resize_native_window(state.text_visible)

    if notify:
        ui.notify(f'Text panels {"shown" if state.text_visible else "hidden"}')


def _resize_native_window(text_visible: bool):
    """Resize native pywebview window to match sidebar/text mode."""
    try:
        window = getattr(app.native, 'main_window', None)
        if not window:
            return
        target_width = 1200 if text_visible else 420
        current_height = getattr(window, 'height', 800) or 800
        window.resize(target_width, current_height)
    except Exception:
        # Ignore resize errors in browser mode or unsupported backends
        return


def _set_section_visual_state(section, enabled: bool):
    """Dim or undim a configuration section without disabling inputs."""
    if not section:
        return
    if enabled:
        section.classes(remove='section-muted')
    else:
        section.classes(add='section-muted')
