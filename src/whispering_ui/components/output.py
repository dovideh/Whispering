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

    output_container = ui.column().classes('flex-grow w-full h-full gap-0').style('height: 100%; min-height: 0; padding: 0;')

    panel_defs = [
        {
            'key': 'whisper',
            'title': 'Whisper Output',
            'placeholder': 'Whisper transcription will appear here...',
            'state_attr': 'whisper_text',
            'count_fn': state.get_whisper_count,
            'cut_type': 'whisper',
            'copy_label': 'Whisper',
        },
        {
            'key': 'ai',
            'title': 'AI Output',
            'placeholder': 'AI processed text will appear here...',
            'state_attr': 'ai_text',
            'count_fn': state.get_ai_count,
            'cut_type': 'ai',
            'copy_label': 'AI',
        },
        {
            'key': 'translation',
            'title': 'Translation Output',
            'placeholder': 'Translation will appear here...',
            'state_attr': 'translation_text',
            'count_fn': state.get_translation_count,
            'cut_type': 'translation',
            'copy_label': 'Translation',
        },
    ]

    textareas = {}
    count_labels = {}

    with output_container:
        stack = ui.column().classes('output-stack w-full h-full flex-1')
        for config in panel_defs:
            with stack:
                panel = ui.element('div').classes('output-panel').style('flex: 1; min-height: 0;')
                with panel:
                    with ui.row().classes('panel-header w-full'):
                        ui.label(config['title']).classes('font-bold')
                        with ui.row().classes('items-center gap-2'):
                            count_labels[config['key']] = ui.label('0 chars, 0 words').classes('text-xs text-gray-500')
                            ui.button(
                                'Copy',
                                on_click=lambda cfg=config: _copy_text(
                                    getattr(state, cfg['state_attr']),
                                    cfg['copy_label']
                                )
                            ).props('dense flat').classes('text-xs')
                            ui.button(
                                'Cut',
                                on_click=lambda cfg=config: _cut_text(
                                    state,
                                    cfg['cut_type'],
                                    textareas[cfg['key']]
                                )
                            ).props('dense flat').classes('text-xs')

                    textareas[config['key']] = ui.textarea(
                        placeholder=config['placeholder']
                    ).classes('w-full h-full flex-1 output-textarea').style('font-family: monospace; min-height: 0; height: 100%;').props('outlined readonly')

        def update_outputs():
            for cfg in panel_defs:
                text_value = getattr(state, cfg['state_attr'])
                area = textareas[cfg['key']]
                if area.value != text_value:
                    area.value = text_value

                chars, words = cfg['count_fn']()
                count_labels[cfg['key']].text = f'{chars} chars, {words} words'

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
