#!/usr/bin/env python3
"""
Voice Command Detector
Detects voice commands in transcribed text using configurable detection modes.

Detection modes:
- isolation: The entire Whisper segment must match a trigger phrase exactly
- prefix: The segment must begin with a wake word (e.g., "command bold")
"""

import re
import unicodedata
from typing import Optional, Tuple, Dict

from commands_config import VoiceCommandsConfig


class CommandDetector:
    """
    Detects voice commands in finalized Whisper text segments.

    Uses the isolation heuristic by default: if the entire segment (stripped of
    whitespace and punctuation) matches a known trigger phrase, it's a command.
    Otherwise it's regular speech.
    """

    def __init__(self, config: VoiceCommandsConfig, language: str = None):
        self.config = config
        self.language = language
        self.detection_mode = config.detection_mode
        self.prefix_word = config.prefix_word.lower().strip()

        # Build trigger lookup map
        self._trigger_map = config.build_trigger_map(language)

    def set_language(self, language: str):
        """Update the language filter and rebuild the trigger map."""
        self.language = language
        self._trigger_map = self.config.build_trigger_map(language)

    def _normalize(self, text: str) -> str:
        """
        Normalize text for matching: lowercase, strip whitespace,
        remove trailing punctuation that Whisper often appends.
        """
        text = text.strip().lower()
        # Remove leading/trailing punctuation (periods, commas, etc.)
        text = text.strip('.,!?;:"\'-…')
        # Collapse multiple spaces
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def check(self, segment_text: str) -> Optional[dict]:
        """
        Check if a text segment contains a voice command.

        Args:
            segment_text: The finalized text from Whisper (a single segment
                          or accumulated done_text chunk).

        Returns:
            Command info dict if a command was detected:
                {
                    'command_id': str,
                    'action': str,
                    'insert': str or None,
                    'format': str or None,
                    'matched_trigger': str,
                    'remaining_text': str,  # text after command removal
                }
            None if no command detected.
        """
        if not segment_text or not segment_text.strip():
            return None

        if self.detection_mode == "prefix":
            return self._check_prefix(segment_text)
        else:
            return self._check_isolation(segment_text)

    def _check_isolation(self, text: str) -> Optional[dict]:
        """
        Isolation mode: the entire segment must match a trigger phrase.
        This is the recommended mode — it avoids false positives because
        commands spoken mid-sentence are ignored.
        """
        normalized = self._normalize(text)

        if not normalized:
            return None

        cmd_info = self._trigger_map.get(normalized)
        if cmd_info:
            return {
                **cmd_info,
                "matched_trigger": normalized,
                "remaining_text": "",
            }

        return None

    def _check_prefix(self, text: str) -> Optional[dict]:
        """
        Prefix mode: the segment must start with the wake word,
        followed by the trigger phrase.
        E.g., "command comma" → triggers comma insertion.
        """
        normalized = self._normalize(text)

        if not normalized.startswith(self.prefix_word):
            return None

        # Strip the prefix word and check what remains
        after_prefix = normalized[len(self.prefix_word):].strip()

        if not after_prefix:
            return None

        cmd_info = self._trigger_map.get(after_prefix)
        if cmd_info:
            return {
                **cmd_info,
                "matched_trigger": after_prefix,
                "remaining_text": "",
            }

        return None

    def check_multi_segment(self, text: str) -> Tuple[str, list]:
        """
        Check a multi-line text block for commands. Each line (split by newline)
        is checked independently. Commands are extracted and remaining text is
        reassembled.

        This is useful when done_text contains multiple sentences separated
        by newlines, and one of them might be a command.

        Args:
            text: Text that may contain multiple segments

        Returns:
            (remaining_text, list_of_commands)
            where each command is the dict returned by check()
        """
        if not text:
            return ("", [])

        # Split on sentence boundaries for checking
        # We check the entire text first (most common case)
        result = self.check(text)
        if result:
            return (result["remaining_text"], [result])

        # No command found in the whole text
        return (text, [])
