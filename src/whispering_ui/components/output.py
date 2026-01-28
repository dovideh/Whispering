#!/usr/bin/env python3
"""
Output Component
Rich text display panels for Whisper, AI, and Translation output with Copy/Cut buttons.

Panels render HTML content inside scrollable containers, supporting formatted text
from voice commands (bold, italic, headings, etc.) while maintaining plain-text
copy/cut via clipboard.
"""

import html
import json
import re
import threading
from nicegui import ui
from whispering_ui.state import AppState


def _copy_to_clipboard_native(text: str) -> bool:
    """Copy text to system clipboard using native tools (not JS).
    Uses the same approach as autotype.py for PyQt6 compatibility."""
    import subprocess
    import shutil

    # Try xclip first (Linux X11)
    if shutil.which("xclip"):
        try:
            proc = subprocess.Popen(
                ["xclip", "-selection", "clipboard"],
                stdin=subprocess.PIPE, stderr=subprocess.DEVNULL
            )
            proc.communicate(input=text.encode("utf-8"))
            if proc.returncode == 0:
                return True
        except Exception:
            pass

    # Try xsel
    if shutil.which("xsel"):
        try:
            proc = subprocess.Popen(
                ["xsel", "--clipboard", "--input"],
                stdin=subprocess.PIPE, stderr=subprocess.DEVNULL
            )
            proc.communicate(input=text.encode("utf-8"))
            if proc.returncode == 0:
                return True
        except Exception:
            pass

    # Try wl-copy (Wayland)
    if shutil.which("wl-copy"):
        try:
            proc = subprocess.Popen(
                ["wl-copy"],
                stdin=subprocess.PIPE, stderr=subprocess.DEVNULL
            )
            proc.communicate(input=text.encode("utf-8"))
            if proc.returncode == 0:
                return True
        except Exception:
            pass

    # Fallback to tkinter
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        root.destroy()
        return True
    except Exception:
        pass

    return False


def _text_to_html(text: str) -> str:
    """
    Convert plain text to safe HTML for display.
    Escapes HTML entities, then converts newlines to <br> tags.
    Preserves any existing HTML tags that were inserted by the command system.
    """
    if not text:
        return ""

    # The text may already contain HTML tags from the command executor (Phase 2).
    # For Phase 1, all text is plain so we escape everything.
    # We escape & < > but preserve newlines as <br>.
    escaped = html.escape(text)
    # Convert \n to <br>
    escaped = escaped.replace("\n", "<br>")
    # Convert \t to spaces for display
    escaped = escaped.replace("\t", "&nbsp;&nbsp;&nbsp;&nbsp;")
    return escaped


def _html_to_plain(html_text: str) -> str:
    """
    Strip HTML tags from text for clipboard operations.
    Converts <br> back to newlines and removes all other tags.
    """
    if not html_text:
        return ""
    # The state stores plain text, so just return it directly
    return html_text


def create_output_panels(state: AppState, bridge=None):
    """
    Create output text panels with Copy/Cut buttons.

    Args:
        state: Application state
        bridge: Processing bridge (optional, needed for audio controls)

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

    html_panels = {}
    count_labels = {}
    title_labels = {}
    # Track previous text values to avoid redundant DOM updates
    _prev_values = {cfg['key']: None for cfg in panel_defs}

    with output_container:
        stack = ui.element('div').classes('output-stack flex flex-col w-full h-full flex-1')
        for config in panel_defs:
            with stack:
                panel = ui.element('div').classes('output-panel').style('flex: 1 1 0; min-height: 0;')
                with panel:
                    with ui.row().classes('panel-header w-full'):
                        title_labels[config['key']] = ui.label(config['title']).classes('font-bold')
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
                                    cfg['key'],
                                    html_panels
                                )
                            ).props('dense flat').classes('text-xs')

                            # Add audio playback controls for AI panel in Q&A mode
                            if config['key'] == 'ai' and bridge:
                                # Play button
                                play_btn = ui.button(
                                    icon='play_arrow',
                                    on_click=lambda b=bridge: b.replay_qa_audio()
                                ).props('dense flat round size=sm').classes('text-xs')
                                play_btn.visible = False  # Initially hidden

                                # Stop button
                                stop_btn = ui.button(
                                    icon='stop',
                                    on_click=lambda b=bridge: b.stop_qa_audio()
                                ).props('dense flat round size=sm').classes('text-xs')
                                stop_btn.visible = False  # Initially hidden

                                # Store references for visibility control
                                config['play_btn'] = play_btn
                                config['stop_btn'] = stop_btn

                    # Rich text panel: scrollable div with HTML content
                    scroll_container = ui.element('div').classes(
                        'w-full flex-1 output-richtext'
                    ).style(
                        'overflow-y: auto; overflow-x: hidden; '
                        'min-height: 0; height: 100%; '
                        'font-family: Menlo, Consolas, "Liberation Mono", monospace; '
                        'font-size: 0.875rem; '
                        'line-height: 1.5; '
                        'padding: 0.25rem 0.4rem; '
                        'color: #e0e0e0; '
                        'user-select: text; '
                        'white-space: pre-wrap; '
                        'word-wrap: break-word; '
                    )

                    with scroll_container:
                        html_panel = ui.html('', sanitize=False).classes('w-full')
                        html_panels[config['key']] = html_panel

        def update_outputs():
            for cfg in panel_defs:
                text_value = getattr(state, cfg['state_attr'])
                key = cfg['key']

                # Only update DOM when value actually changed
                if _prev_values[key] != text_value:
                    _prev_values[key] = text_value
                    if text_value:
                        html_content = _text_to_html(text_value)
                    else:
                        html_content = (
                            f'<span style="color: #666; font-style: italic;">'
                            f'{html.escape(cfg["placeholder"])}</span>'
                        )
                    html_panels[key].content = html_content

                    # Auto-scroll to bottom
                    html_panels[key].run_method(
                        'scrollIntoView',
                        False  # alignToTop=False -> scroll to bottom
                    )

                chars, words = cfg['count_fn']()
                count_labels[key].text = f'{chars} chars, {words} words'

                # Update AI panel title dynamically
                if key == 'ai':
                    task_name = state.get_current_ai_task_name()
                    if task_name:
                        title_labels[key].text = f"AI Output - {task_name}"
                    else:
                        title_labels[key].text = cfg['title']

                # Update audio playback controls visibility for AI panel
                if key == 'ai' and 'play_btn' in cfg and 'stop_btn' in cfg:
                    # Show controls if TTS is enabled, source is AI, and we have an audio file
                    show_controls = (
                        state.tts_enabled and
                        state.tts_source == 'ai' and
                        state.tts_audio_file is not None
                    )
                    cfg['play_btn'].visible = show_controls and not state.tts_is_playing
                    cfg['stop_btn'].visible = show_controls and state.tts_is_playing

        ui.timer(0.2, update_outputs)

    return output_container


def _copy_text(text: str, label: str):
    """Copy text to system clipboard using native tools."""
    text_to_copy = str(text) if text else ""

    if not text_to_copy.strip():
        ui.notify(f'No {label} text to copy', type='warning')
        return

    def do_copy():
        success = _copy_to_clipboard_native(text_to_copy)
        if not success:
            print(f"Clipboard copy failed for {label}")

    # Run clipboard operation in background thread to avoid blocking UI
    threading.Thread(target=do_copy, daemon=True).start()
    ui.notify(f'Copied {label} text to clipboard', type='positive')


def _cut_text(state: AppState, text_type: str, panel_key: str, html_panels: dict):
    """Cut text (copy to clipboard and clear panel)."""
    if text_type == 'whisper':
        text = str(state.whisper_text) if state.whisper_text else ""
    elif text_type == 'ai':
        text = str(state.ai_text) if state.ai_text else ""
    elif text_type == 'translation':
        text = str(state.translation_text) if state.translation_text else ""
    else:
        return

    if not text.strip():
        ui.notify(f'No text to cut', type='warning')
        return

    def do_copy():
        success = _copy_to_clipboard_native(text)
        if not success:
            print(f"Clipboard cut failed for {text_type}")

    threading.Thread(target=do_copy, daemon=True).start()

    # Clear the text in state
    if text_type == 'whisper':
        state.whisper_text = ""
    elif text_type == 'ai':
        state.ai_text = ""
    elif text_type == 'translation':
        state.translation_text = ""

    # Clear HTML panel
    try:
        if panel_key in html_panels:
            html_panels[panel_key].content = ""
    except Exception:
        pass

    ui.notify(f'Cut text to clipboard', type='positive')
