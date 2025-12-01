#!/usr/bin/env python3
"""
Simplified Sidebar Component
Control panel with all settings and controls - uses direct state updates
"""

from nicegui import ui
import core
from ..state import AppState
from ..bridge import ProcessingBridge


def create_sidebar(state: AppState, bridge: ProcessingBridge):
    """
    Create the sidebar control panel with simplified bindings.

    Args:
        state: Application state
        bridge: Processing bridge
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
            on_click=lambda: _toggle_text(state, toggle_btn)
        ).classes('w-full mb-2')

        ui.separator().classes('my-2')

        # === MODEL SECTION ===
        ui.label('Model Settings').classes('font-bold')

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

        ai_cb = ui.checkbox('Enable AI', value=state.ai_enabled)
        ai_cb.on_value_change(lambda e: setattr(state, 'ai_enabled', e.value))
        if not state.ai_available:
            ai_cb.disable()

        if state.ai_available:
            try:
                from ai_config import load_ai_config
                ai_config = load_ai_config()
                if ai_config:
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
            except:
                pass

        ai_trans_cb = ui.checkbox('Translate output', value=state.ai_translate)
        ai_trans_cb.on_value_change(lambda e: setattr(state, 'ai_translate', e.value))
        if not state.ai_available:
            ai_trans_cb.disable()

        ui.separator().classes('my-2')

        # === TTS SECTION ===
        ui.label('Text-to-Speech').classes('font-bold')

        tts_cb = ui.checkbox('Enable TTS', value=state.tts_enabled)
        tts_cb.on_value_change(lambda e: setattr(state, 'tts_enabled', e.value))
        if not state.tts_available:
            tts_cb.disable()

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

            # Update level
            level_progress.value = state.audio_level / 100.0

            # Update status
            if state.error_message:
                status_label.text = f'Error: {state.error_message}'
            elif state.status_message:
                status_label.text = state.status_message
            else:
                status_label.text = ''

        ui.timer(0.1, update_ui)


def _toggle_text(state: AppState, btn):
    """Toggle text visibility."""
    state.text_visible = not state.text_visible
    btn.text = 'Hide Text ◀' if state.text_visible else 'Show Text ▶'
    ui.notify(f'Text panels {"shown" if state.text_visible else "hidden"}')


def _toggle_recording(state: AppState, bridge: ProcessingBridge, btn, level, status):
    """Toggle recording on/off."""
    if state.is_recording:
        bridge.stop_recording()
    else:
        bridge.start_recording()
