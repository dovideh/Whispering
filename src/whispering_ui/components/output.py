#!/usr/bin/env python3
"""
Output Component
Text display panels for Whisper, AI, and Translation output with Copy/Cut buttons
"""

from nicegui import ui
from whispering_ui.state import AppState


def create_output_panels(state: AppState):
    """
    Create output text panels with Copy/Cut buttons.

    Args:
        state: Application state

    Returns:
        The output container element for visibility control
    """

    output_container = ui.column().classes('flex-grow p-4 gap-3')

    with output_container:
        # === WHISPER OUTPUT ===
        with ui.column().classes('flex-grow'):
            with ui.row().classes('items-center justify-between w-full mb-1'):
                ui.label('Whisper Output').classes('font-bold')

                # Count and buttons
                with ui.row().classes('items-center gap-2'):
                    whisper_count = ui.label('0 chars, 0 words').classes('text-xs text-gray-500')
                    ui.button('Copy', on_click=lambda: _copy_text(state.whisper_text, 'Whisper')).props('dense flat').classes('text-xs')
                    ui.button('Cut', on_click=lambda: _cut_text(state, 'whisper', whisper_area)).props('dense flat').classes('text-xs')

            whisper_area = ui.textarea(
                placeholder='Whisper transcription will appear here...'
            ).classes('w-full').style('min-height: 200px; font-family: monospace;').props('outlined readonly')

        # === AI OUTPUT ===
        with ui.column().classes('flex-grow'):
            with ui.row().classes('items-center justify-between w-full mb-1'):
                ui.label('AI Output').classes('font-bold')

                # Count and buttons
                with ui.row().classes('items-center gap-2'):
                    ai_count = ui.label('0 chars, 0 words').classes('text-xs text-gray-500')
                    ui.button('Copy', on_click=lambda: _copy_text(state.ai_text, 'AI')).props('dense flat').classes('text-xs')
                    ui.button('Cut', on_click=lambda: _cut_text(state, 'ai', ai_area)).props('dense flat').classes('text-xs')

            ai_area = ui.textarea(
                placeholder='AI processed text will appear here...'
            ).classes('w-full').style('min-height: 200px; font-family: monospace;').props('outlined readonly')

        # === TRANSLATION OUTPUT ===
        with ui.column().classes('flex-grow'):
            with ui.row().classes('items-center justify-between w-full mb-1'):
                ui.label('Translation Output').classes('font-bold')

                # Count and buttons
                with ui.row().classes('items-center gap-2'):
                    trans_count = ui.label('0 chars, 0 words').classes('text-xs text-gray-500')
                    ui.button('Copy', on_click=lambda: _copy_text(state.translation_text, 'Translation')).props('dense flat').classes('text-xs')
                    ui.button('Cut', on_click=lambda: _cut_text(state, 'translation', trans_area)).props('dense flat').classes('text-xs')

            trans_area = ui.textarea(
                placeholder='Translation will appear here...'
            ).classes('w-full').style('min-height: 200px; font-family: monospace;').props('outlined readonly')

        # Update text areas from state
        def update_outputs():
            # Update whisper
            if whisper_area.value != state.whisper_text:
                whisper_area.value = state.whisper_text
            wc, ww = state.get_whisper_count()
            whisper_count.text = f'{wc} chars, {ww} words'

            # Update AI
            if ai_area.value != state.ai_text:
                ai_area.value = state.ai_text
            ac, aw = state.get_ai_count()
            ai_count.text = f'{ac} chars, {aw} words'

            # Update translation
            if trans_area.value != state.translation_text:
                trans_area.value = state.translation_text
            tc, tw = state.get_translation_count()
            trans_count.text = f'{tc} chars, {tw} words'

        ui.timer(0.2, update_outputs)

    return output_container


def _copy_text(text: str, label: str):
    """Copy text to clipboard."""
    if not text.strip():
        ui.notify(f'No {label} text to copy', type='warning')
        return

    try:
        # Use JavaScript clipboard API via ui.run_javascript
        import json
        escaped_text = json.dumps(text)
        ui.run_javascript(f'navigator.clipboard.writeText({escaped_text})')
        ui.notify(f'✓ Copied {label} text to clipboard', type='positive')
    except Exception as e:
        ui.notify(f'Clipboard error: {e}', type='negative')


def _cut_text(state: AppState, text_type: str, textarea):
    """Cut text (copy and clear)."""
    # Get the text
    if text_type == 'whisper':
        text = state.whisper_text
    elif text_type == 'ai':
        text = state.ai_text
    elif text_type == 'translation':
        text = state.translation_text
    else:
        return

    if not text.strip():
        ui.notify(f'No text to cut', type='warning')
        return

    try:
        # Copy to clipboard
        import json
        escaped_text = json.dumps(text)
        ui.run_javascript(f'navigator.clipboard.writeText({escaped_text})')

        # Clear the text
        if text_type == 'whisper':
            state.whisper_text = ""
        elif text_type == 'ai':
            state.ai_text = ""
        elif text_type == 'translation':
            state.translation_text = ""

        # Update textarea
        textarea.value = ""

        ui.notify(f'✓ Cut text to clipboard', type='positive')
    except Exception as e:
        ui.notify(f'Clipboard error: {e}', type='negative')
