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

            # Log to file checkbox
            log_cb = ui.checkbox('Save logs', value=state.log_enabled).props('dense')
            log_cb.on_value_change(lambda e: setattr(state, 'log_enabled', e.value))

        # Status - compact
        status_label = ui.label('').classes('text-xs text-red-400 mt-1')

        ui.separator().classes('my-1')

        # === FILE TRANSCRIPTION SECTION ===
        with ui.row().classes('items-center justify-between w-full'):
            ui.label('File Transcription').classes('font-bold text-sm')
            ui.button(icon='help_outline', on_click=lambda: show_help_dialog('file_transcription')).props('flat dense round size=sm')

        # Recovery notification (shown if recovery data exists)
        recovery_row = ui.row().classes('items-center w-full gap-1 bg-yellow-900 p-1 rounded')
        recovery_row.set_visibility(False)

        with recovery_row:
            ui.icon('warning', color='yellow').classes('text-sm')
            recovery_label = ui.label('Recovery available').classes('text-xs text-yellow-200 flex-grow')
            ui.button('Resume', on_click=lambda: _apply_recovery(state, bridge, recovery_row, update_file_list_display)).props('dense size=sm color=warning')
            ui.button('Discard', on_click=lambda: _discard_recovery(state, bridge, recovery_row)).props('dense size=sm flat')

        # Check for recovery on load
        def check_recovery():
            if bridge.check_recovery_available():
                recovery_state = bridge.load_recovery_state()
                if recovery_state:
                    pos = recovery_state.get('position', 0)
                    recovery_label.text = f"Resume from {_format_time(pos)}"
                    recovery_row.set_visibility(True)

        ui.timer(0.5, check_recovery, once=True)

        # File selection controls
        file_list_label = ui.label('No files selected').classes('text-xs text-gray-400 truncate w-full')

        def update_file_list_display():
            """Update the file list display."""
            count = len(state.file_transcription_paths)
            if count == 0:
                file_list_label.text = 'No files selected'
                duration_label.text = ''
            elif count == 1:
                import os
                file_list_label.text = os.path.basename(state.file_transcription_paths[0])
                # Get and display duration
                try:
                    dur = bridge.get_file_duration(state.file_transcription_paths[0])
                    duration_label.text = f'Duration: {_format_time(dur)}'
                except Exception:
                    duration_label.text = ''
            else:
                file_list_label.text = f'{count} files selected'
                duration_label.text = ''

        # File upload for multiple files
        def on_file_upload(e):
            """Handle file upload for transcription."""
            try:
                import os
                from pathlib import Path

                # Create uploads directory if needed
                uploads_dir = Path("uploads")
                uploads_dir.mkdir(exist_ok=True)

                # Read and save uploaded file
                filename = Path(e.name).name
                permanent_path = uploads_dir / filename

                with open(e.name, 'rb') as f:
                    content = f.read()

                with open(permanent_path, 'wb') as f:
                    f.write(content)

                # Add to transcription list
                if core.is_audio_file(str(permanent_path)):
                    state.file_transcription_paths.append(str(permanent_path))
                    update_file_list_display()
                    ui.notify(f"Added: {filename}", type='positive')
                else:
                    ui.notify(f"Not an audio file: {filename}", type='warning')
            except Exception as ex:
                ui.notify(f"Error: {ex}", type='negative')

        with ui.row().classes('items-center w-full gap-1'):
            # Hidden file upload
            file_upload = ui.upload(
                on_upload=on_file_upload,
                auto_upload=True,
                max_file_size=500_000_000,  # 500MB
                multiple=True
            ).props('accept=audio/*').classes('hidden')

            ui.button('Add Files', on_click=lambda: file_upload.run_method('pickFiles')).classes('flex-grow').props('dense')
            ui.button(icon='clear', on_click=lambda: _clear_file_list(state, bridge, file_list_label, update_file_list_display)).props('flat dense round size=sm')

        # Duration display
        duration_label = ui.label('').classes('text-xs text-gray-400')

        # Time range controls
        with ui.row().classes('items-center w-full gap-1'):
            ui.label('Range:').classes('text-xs w-12')

            # Start time input
            start_input = ui.input(
                value='0:00',
                on_change=lambda e: _parse_time_input(e.value, state, 'start')
            ).classes('w-16').props('dense')
            start_input.tooltip('Start time (M:SS or H:MM:SS)')

            ui.label('→').classes('text-xs')

            # End time input
            end_input = ui.input(
                value='end',
                on_change=lambda e: _parse_time_input(e.value, state, 'end')
            ).classes('w-16').props('dense')
            end_input.tooltip('End time (M:SS, H:MM:SS, or "end")')

            # Play button for scrubbing
            play_btn = ui.button(icon='play_arrow', on_click=lambda: _play_audio_preview(state, bridge)).props('flat dense round size=sm')
            play_btn.tooltip('Preview audio')

            stop_play_btn = ui.button(icon='stop', on_click=lambda: bridge.stop_audio_playback()).props('flat dense round size=sm')
            stop_play_btn.tooltip('Stop preview')

        # Progress bar for file transcription
        file_progress = ui.linear_progress(value=0, show_value=False).classes('w-full')
        file_progress.set_visibility(False)

        # Current file being processed
        file_current_label = ui.label('').classes('text-xs text-blue-400 truncate w-full')

        # Save indicator - "Saved at: HH:MM:SS ...last words"
        save_indicator = ui.label('').classes('text-xs text-green-400 truncate w-full')

        # Start/Stop file transcription buttons
        with ui.row().classes('items-center w-full gap-1'):
            file_start_btn = ui.button(
                'Transcribe',
                on_click=lambda: _start_file_transcription(state, bridge, file_start_btn, file_stop_btn, file_progress)
            ).classes('flex-grow').props('dense color=positive')

            file_stop_btn = ui.button(
                'Stop',
                on_click=lambda: _stop_file_transcription(state, bridge, file_start_btn, file_stop_btn, file_progress)
            ).classes('w-16').props('dense color=negative')
            file_stop_btn.set_enabled(False)

        # Update file transcription UI periodically
        def update_file_ui():
            if state.file_transcription_active:
                file_progress.set_visibility(True)
                file_progress.value = state.file_transcription_progress / 100.0
                file_current_label.text = f"Processing: {state.file_transcription_current_file}" if state.file_transcription_current_file else ""
                file_start_btn.set_enabled(False)
                file_stop_btn.set_enabled(True)

                # Update save indicator
                if state.file_last_saved_time:
                    save_indicator.text = f"Saved {state.file_last_saved_time}: {state.file_last_saved_text}"
                else:
                    save_indicator.text = ""
            else:
                file_progress.set_visibility(state.file_transcription_progress > 0 and state.file_transcription_progress < 100)
                file_current_label.text = ""
                file_start_btn.set_enabled(len(state.file_transcription_paths) > 0)
                file_stop_btn.set_enabled(False)

                # Keep save indicator visible after completion
                if state.file_last_saved_time and state.file_transcription_progress == 100:
                    save_indicator.text = f"Saved {state.file_last_saved_time}: {state.file_last_saved_text}"

            # Update play button state
            play_btn.set_enabled(len(state.file_transcription_paths) > 0 and not state.file_playback_active)
            stop_play_btn.set_enabled(state.file_playback_active)

        ui.timer(0.2, update_file_ui)

        ui.separator().classes('my-1')

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
            ui.label('Source:').classes('text-xs w-14')
            src_select = ui.select(
                options=["auto"] + core.sources,
                value=state.source_language
            ).classes('w-20').props('dense')
            src_select.on_value_change(lambda e: setattr(state, 'source_language', e.value))

            ui.label('Target:').classes('text-xs w-14')
            tgt_select = ui.select(
                options=["none"] + core.targets,
                value=state.target_language
            ).classes('w-20').props('dense')
            tgt_select.on_value_change(lambda e: setattr(state, 'target_language', e.value))

        # Translation provider hint
        translation_hint = ui.label('').classes('text-xs text-gray-400 italic')

        def update_translation_hint():
            """Update the translation provider hint based on current settings."""
            if state.target_language == "none":
                translation_hint.text = ""
            elif state.ai_enabled and (state.ai_translate or state.ai_translate_only):
                translation_hint.text = f"→ AI translates to {state.target_language.upper()}"
            elif state.target_language != "none":
                translation_hint.text = f"→ Google Translate to {state.target_language.upper()}"
            else:
                translation_hint.text = ""

        # Update hint when relevant values change
        ui.timer(0.2, update_translation_hint)

        ui.separator().classes('my-1')

        # === AI & TTS LEFT DRAWER PANEL ===
        # Create a dialog positioned on the left side that acts as a drawer
        ai_tts_drawer = ui.dialog().props('position=left full-height seamless')
        ai_tts_drawer_visible = [False]

        def toggle_ai_tts_drawer():
            ai_tts_drawer_visible[0] = not ai_tts_drawer_visible[0]
            if ai_tts_drawer_visible[0]:
                ai_tts_drawer.open()
                ai_tts_toggle_btn.text = 'AI & TTS ◀'
            else:
                ai_tts_drawer.close()
                ai_tts_toggle_btn.text = 'AI & TTS ▶'

        # Handle drawer close via clicking outside
        def on_drawer_hide():
            ai_tts_drawer_visible[0] = False
            ai_tts_toggle_btn.text = 'AI & TTS ▶'

        ai_tts_drawer.on('hide', on_drawer_hide)

        # Row with button and status indicators
        with ui.row().classes('items-center w-full gap-1'):
            ai_tts_toggle_btn = ui.button(
                'AI & TTS ▶',
                on_click=toggle_ai_tts_drawer
            ).classes('flex-grow').props('dense flat')

            # Status indicators
            ai_indicator = ui.label('AI').classes('text-xs px-1 rounded')
            tts_indicator = ui.label('TTS').classes('text-xs px-1 rounded')

            def update_indicators():
                """Update AI/TTS status indicators."""
                if state.ai_enabled and state.ai_available:
                    ai_indicator.classes(remove='bg-gray-600 text-gray-400')
                    ai_indicator.classes(add='bg-green-700 text-white')
                else:
                    ai_indicator.classes(remove='bg-green-700 text-white')
                    ai_indicator.classes(add='bg-gray-600 text-gray-400')

                if state.tts_enabled and state.tts_available:
                    tts_indicator.classes(remove='bg-gray-600 text-gray-400')
                    tts_indicator.classes(add='bg-green-700 text-white')
                else:
                    tts_indicator.classes(remove='bg-green-700 text-white')
                    tts_indicator.classes(add='bg-gray-600 text-gray-400')

            # Initial state
            update_indicators()

            # Periodic update for indicator state
            ui.timer(0.3, update_indicators)

        # Drawer content
        with ai_tts_drawer, ui.card().classes('h-full w-80 p-3 gap-1').style('overflow-y: auto;'):
            # Close button at top
            with ui.row().classes('items-center justify-between w-full mb-2'):
                ui.label('AI & TTS Settings').classes('font-bold text-sm')
                ui.button(icon='close', on_click=lambda: (ai_tts_drawer.close(), setattr(ai_tts_toggle_btn, 'text', 'AI & TTS ▶'))).props('flat dense round size=sm')
            # === AI SECTION ===
            with ui.row().classes('items-center justify-between w-full'):
                ui.label('AI Processing').classes('font-bold text-sm')
                if state.ai_available:
                    ui.button(icon='help_outline', on_click=lambda: show_help_dialog('ai')).props('flat dense round size=sm')

            # Enable AI checkbox
            ai_cb = ui.checkbox('Enable AI', value=state.ai_enabled).props('dense')
            ai_section = ui.column().classes('w-full gap-1')
            ai_controls = []
            ai_process_btn = None
            ai_trigger_select = None
            ai_interval_select = None
            ai_words_num = None

            def register_ai(control):
                ai_controls.append(control)
                return control

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
                                task_select = register_ai(ui.select(
                                    options=persona_names,
                                    value=persona_names[min(state.ai_persona_index, len(persona_names)-1)]
                                ).classes('flex-grow').props('dense'))
                                task_select.on_value_change(lambda e: setattr(state, 'ai_persona_index',
                                                            persona_names.index(e.value) if e.value in persona_names else 0))

                            # Translate checkboxes - compact
                            with ui.row().classes('items-center w-full gap-2'):
                                ai_trans_cb = register_ai(ui.checkbox('Translate', value=state.ai_translate).props('dense'))
                                ai_trans_cb.on_value_change(lambda e: setattr(state, 'ai_translate', e.value))

                                ai_trans_only_cb = register_ai(ui.checkbox('Only (1:1)', value=state.ai_translate_only).props('dense'))
                                ai_trans_only_cb.on_value_change(lambda e: setattr(state, 'ai_translate_only', e.value))

                            # Model selection
                            models = ai_config.get_models()
                            model_names = [m['name'] for m in models]

                            with ui.row().classes('items-center w-full gap-1'):
                                ui.label('Model:').classes('text-xs w-12')
                                ai_model_combo = register_ai(ui.select(
                                    options=model_names,
                                    value=model_names[min(state.ai_model_index, len(model_names)-1)]
                                ).classes('flex-grow').props('dense'))
                                ai_model_combo.on_value_change(lambda e: setattr(state, 'ai_model_index',
                                                               model_names.index(e.value) if e.value in model_names else 0))

                            # Trigger controls - compact layout
                            ai_manual_cb = register_ai(ui.checkbox('Manual mode', value=state.ai_manual_mode).props('dense'))

                            ai_process_btn = register_ai(ui.button('⚡ Process Now', on_click=lambda: bridge.manual_ai_trigger()).classes('w-full').props('dense'))
                            ai_process_btn.set_enabled(state.ai_manual_mode)

                            # Trigger mode and settings
                            with ui.row().classes('items-center w-full gap-1'):
                                ui.label('Trigger:').classes('text-xs')
                                ai_trigger_select = register_ai(ui.select(
                                    options=["Time", "Words"],
                                    value=state.ai_trigger_mode.capitalize()
                                ).classes('w-16').props('dense'))
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
                                ai_interval_select = register_ai(ui.select(
                                    options=interval_labels,
                                    value=current_label
                                ).classes('w-14').props('dense'))

                                def on_interval_change(e):
                                    state.ai_process_interval = interval_map.get(e.value, 20)

                                ai_interval_select.on_value_change(on_interval_change)
                                ai_interval_select.set_enabled(not state.ai_manual_mode)
                                ai_interval_select.set_visibility(state.ai_trigger_mode == "time")

                                ui.label('W:').classes('text-xs')
                                ai_words_num = register_ai(ui.number(value=state.ai_process_words, min=50, max=500, step=50).classes('w-16').props('dense'))
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

            def on_ai_toggle(e):
                state.ai_enabled = e.value
                active = e.value and state.ai_available
                _set_section_visual_state(ai_section, active)
                _set_controls_enabled(ai_controls, active)
                if active and state.ai_available and all(ctrl is not None for ctrl in (ai_process_btn, ai_trigger_select, ai_interval_select, ai_words_num)):
                    _on_manual_mode_changed(state, state.ai_manual_mode, ai_process_btn, ai_trigger_select, ai_interval_select, ai_words_num)
                    _on_trigger_changed(state, state.ai_trigger_mode.capitalize(), ai_interval_select, ai_words_num)

            ai_cb.on_value_change(on_ai_toggle)
            if not state.ai_available:
                ai_cb.disable()

            _set_section_visual_state(ai_section, state.ai_enabled and state.ai_available)
            _set_controls_enabled(ai_controls, state.ai_enabled and state.ai_available)

            ui.separator().classes('my-1')

            # === TTS SECTION ===
            with ui.row().classes('items-center justify-between w-full'):
                ui.label('Text-to-Speech').classes('font-bold text-sm')
                if state.tts_available:
                    ui.button(icon='help_outline', on_click=lambda: show_help_dialog('tts')).props('flat dense round size=sm')

            # Enable TTS
            tts_cb = ui.checkbox('Enable TTS', value=state.tts_enabled).props('dense')
            tts_section = ui.column().classes('w-full gap-1')
            tts_controls = []

            def register_tts(control):
                tts_controls.append(control)
                return control

            if state.tts_available:
                with tts_section:
                    # Source selection - compact
                    with ui.row().classes('items-center w-full gap-1'):
                        ui.label('Src:').classes('text-xs w-10')

                        tts_w_cb = register_tts(ui.checkbox('W', value=(state.tts_source == "whisper")).props('dense'))
                        tts_a_cb = register_tts(ui.checkbox('A', value=(state.tts_source == "ai")).props('dense'))
                        tts_t_cb = register_tts(ui.checkbox('T', value=(state.tts_source == "translation")).props('dense'))

                        tts_w_cb.on_value_change(lambda e: _on_tts_source_changed(state, "whisper", e.value, tts_w_cb, tts_a_cb, tts_t_cb))
                        tts_a_cb.on_value_change(lambda e: _on_tts_source_changed(state, "ai", e.value, tts_w_cb, tts_a_cb, tts_t_cb))
                        tts_t_cb.on_value_change(lambda e: _on_tts_source_changed(state, "translation", e.value, tts_w_cb, tts_a_cb, tts_t_cb))

                    # Voice selection with streamlined upload
                    with ui.row().classes('items-center w-full gap-1'):
                        ui.label('Voice:').classes('text-xs w-10')
                        tts_voice_label = ui.label(state.tts_voice_display_name).classes('flex-grow text-xs text-gray-400 truncate')

                        upload = register_tts(ui.upload(
                            on_upload=lambda e: _on_voice_upload(e, state, bridge, tts_voice_label),
                            auto_upload=True,
                            max_file_size=50_000_000,
                            max_files=1
                        ).props('accept=audio/*').classes('hidden'))

                        register_tts(ui.button(icon='folder_open', on_click=lambda u=upload: u.run_method('pickFiles')).props('flat dense round size=sm'))
                        register_tts(ui.button(icon='clear', on_click=lambda: _clear_voice(state, bridge, tts_voice_label)).props('flat dense round size=sm'))

                    # Output options - compact
                    with ui.row().classes('items-center w-full gap-1'):
                        ui.label('Out:').classes('text-xs w-10')
                        tts_save_cb = register_tts(ui.checkbox('Save', value=state.tts_save_file).props('dense'))
                        tts_save_cb.on_value_change(lambda e: setattr(state, 'tts_save_file', e.value))

                        tts_format_select = register_tts(ui.select(options=["wav", "ogg"], value=state.tts_format).classes('w-16').props('dense'))
                        tts_format_select.on_value_change(lambda e: setattr(state, 'tts_format', e.value))

                    # TTS status - compact
                    tts_status_label = ui.label('').classes('text-xs text-blue-400')

                    def update_tts_status():
                        if state.tts_status_message:
                            tts_status_label.text = state.tts_status_message[:50]
                        else:
                            tts_status_label.text = ''

                    ui.timer(0.2, update_tts_status)

            def on_tts_toggle(e):
                state.tts_enabled = e.value
                active = e.value and state.tts_available
                _set_section_visual_state(tts_section, active)
                _set_controls_enabled(tts_controls, active)

            tts_cb.on_value_change(on_tts_toggle)
            if not state.tts_available:
                tts_cb.disable()

            _set_section_visual_state(tts_section, state.tts_enabled and state.tts_available)
            _set_controls_enabled(tts_controls, state.tts_enabled and state.tts_available)

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


def _set_controls_enabled(controls, enabled: bool):
    """Enable or disable a list of controls."""
    for ctrl in controls:
        if ctrl is None:
            continue
        try:
            ctrl.set_enabled(enabled)
        except AttributeError:
            try:
                (ctrl.enable() if enabled else ctrl.disable())
            except AttributeError:
                if enabled:
                    ctrl.props(remove='disable')
                else:
                    ctrl.props('disable')


def _clear_file_list(state: AppState, bridge: ProcessingBridge, file_list_label, update_fn):
    """Clear the file transcription list."""
    bridge.clear_file_list()
    update_fn()
    ui.notify("File list cleared")


def _start_file_transcription(state: AppState, bridge: ProcessingBridge, start_btn, stop_btn, progress):
    """Start file transcription."""
    if not state.file_transcription_paths:
        ui.notify("No files selected", type='warning')
        return

    if state.is_recording:
        ui.notify("Stop microphone recording first", type='warning')
        return

    bridge.start_file_transcription(state.file_transcription_paths)
    start_btn.set_enabled(False)
    stop_btn.set_enabled(True)
    progress.set_visibility(True)
    ui.notify(f"Starting transcription of {len(state.file_transcription_paths)} file(s)")


def _stop_file_transcription(state: AppState, bridge: ProcessingBridge, start_btn, stop_btn, progress):
    """Stop file transcription."""
    bridge.stop_file_transcription()
    start_btn.set_enabled(True)
    stop_btn.set_enabled(False)
    ui.notify("File transcription stopped")


def _format_time(seconds: float) -> str:
    """Format seconds as M:SS or H:MM:SS."""
    if seconds is None:
        return "end"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _parse_time_input(value: str, state: AppState, field: str):
    """Parse time input and update state.

    Args:
        value: Time string (M:SS, H:MM:SS, or 'end')
        state: AppState to update
        field: 'start' or 'end'
    """
    if not value or value.lower() == 'end':
        if field == 'end':
            state.file_end_time = None
        return

    try:
        parts = value.split(':')
        if len(parts) == 2:
            # M:SS format
            minutes, seconds = int(parts[0]), int(parts[1])
            total_seconds = minutes * 60 + seconds
        elif len(parts) == 3:
            # H:MM:SS format
            hours, minutes, seconds = int(parts[0]), int(parts[1]), int(parts[2])
            total_seconds = hours * 3600 + minutes * 60 + seconds
        else:
            # Try parsing as seconds
            total_seconds = float(value)

        if field == 'start':
            state.file_start_time = max(0.0, total_seconds)
        else:
            state.file_end_time = total_seconds if total_seconds > 0 else None
    except (ValueError, IndexError):
        pass  # Invalid format, ignore


def _apply_recovery(state: AppState, bridge: ProcessingBridge, recovery_row, update_fn):
    """Apply recovery state."""
    if bridge.apply_recovery():
        recovery_row.set_visibility(False)
        update_fn()
        ui.notify(f"Recovery applied - starting from {_format_time(state.file_start_time)}", type='positive')
    else:
        ui.notify("Failed to apply recovery", type='warning')


def _discard_recovery(state: AppState, bridge: ProcessingBridge, recovery_row):
    """Discard recovery state."""
    bridge.discard_recovery()
    recovery_row.set_visibility(False)
    ui.notify("Recovery discarded")


def _play_audio_preview(state: AppState, bridge: ProcessingBridge):
    """Play audio file for preview/scrubbing."""
    if not state.file_transcription_paths:
        return

    file_path = state.file_transcription_paths[0]
    start_time = state.file_start_time

    bridge.play_audio_file(file_path, start_time)
    ui.notify(f"Playing from {_format_time(start_time)}")
