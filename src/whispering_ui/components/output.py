#!/usr/bin/env python3
"""
Simplified Output Component
Text display panels for Whisper, AI, and Translation output
"""

from nicegui import ui
from whispering_ui.state import AppState


def create_output_panels(state: AppState):
    """
    Create output text panels with simplified updates.

    Args:
        state: Application state
    """

    output_container = ui.column().classes('flex-grow p-4 gap-3')

    with output_container:
        # === WHISPER OUTPUT ===
        with ui.column().classes('flex-grow'):
            with ui.row().classes('items-center justify-between w-full mb-1'):
                ui.label('Whisper Output').classes('font-bold')
                whisper_count = ui.label('0 chars, 0 words').classes('text-xs text-gray-500')

            whisper_area = ui.textarea(
                placeholder='Whisper transcription will appear here...'
            ).classes('w-full').style('min-height: 200px; font-family: monospace;').props('outlined readonly')

        # === AI OUTPUT ===
        with ui.column().classes('flex-grow'):
            with ui.row().classes('items-center justify-between w-full mb-1'):
                ui.label('AI Output').classes('font-bold')
                ai_count = ui.label('0 chars, 0 words').classes('text-xs text-gray-500')

            ai_area = ui.textarea(
                placeholder='AI processed text will appear here...'
            ).classes('w-full').style('min-height: 200px; font-family: monospace;').props('outlined readonly')

        # === TRANSLATION OUTPUT ===
        with ui.column().classes('flex-grow'):
            with ui.row().classes('items-center justify-between w-full mb-1'):
                ui.label('Translation Output').classes('font-bold')
                trans_count = ui.label('0 chars, 0 words').classes('text-xs text-gray-500')

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
