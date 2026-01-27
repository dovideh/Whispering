#!/usr/bin/env python3
"""
Voice Command Executor
Dispatches detected commands to their appropriate actions:
- insert_text: substitute the trigger with a text string (punctuation, whitespace)
- format_toggle: toggle a formatting state (Phase 2)
- format_block: apply block-level formatting (Phase 2)
"""

from typing import Optional
from debug import debug_print


class CommandExecutor:
    """
    Executes voice commands by producing text substitutions
    and/or triggering autotype keystrokes.
    """

    def __init__(self):
        # Track last executed command for debugging
        self.last_command = None
        self.last_result = None

    def execute(self, command: dict) -> Optional[str]:
        """
        Execute a detected command.

        Args:
            command: Command info dict from CommandDetector.check():
                {
                    'command_id': str,
                    'action': str,
                    'insert': str or None,
                    'format': str or None,
                    'matched_trigger': str,
                    'remaining_text': str,
                }

        Returns:
            Text to insert into the output buffer (replaces the command segment),
            or None if the command produces no text (e.g., a keystroke-only action).
        """
        if not command:
            return None

        action = command.get("action", "")
        self.last_command = command

        if action == "insert_text":
            result = self._execute_insert_text(command)
        elif action == "format_toggle":
            result = self._execute_format_toggle(command)
        elif action == "format_block":
            result = self._execute_format_block(command)
        else:
            debug_print(f"[CMD] Unknown action type: {action}")
            result = None

        self.last_result = result
        return result

    def _execute_insert_text(self, command: dict) -> Optional[str]:
        """
        Insert text action: replace the voice command with a text string.
        E.g., "comma" -> ","
        """
        insert = command.get("insert", "")
        cmd_id = command.get("command_id", "?")

        if insert is not None:
            debug_print(f"[CMD] insert_text: '{cmd_id}' -> '{insert}'")
            return insert

        debug_print(f"[CMD] insert_text: '{cmd_id}' has no insert value")
        return None

    def _execute_format_toggle(self, command: dict) -> Optional[str]:
        """
        Format toggle action (Phase 2 placeholder).
        E.g., "bold" toggles bold formatting on/off.
        """
        fmt = command.get("format", "?")
        debug_print(f"[CMD] format_toggle: '{fmt}' (Phase 2 - not yet implemented)")
        return None

    def _execute_format_block(self, command: dict) -> Optional[str]:
        """
        Format block action (Phase 2 placeholder).
        E.g., "heading 1" applies H1 to the next paragraph.
        """
        fmt = command.get("format", "?")
        debug_print(f"[CMD] format_block: '{fmt}' (Phase 2 - not yet implemented)")
        return None

    def execute_autotype_keys(self, keys: str) -> bool:
        """
        Send a keystroke sequence to the focused application via autotype.
        Used for formatting commands that need to send Ctrl+B, etc.

        Args:
            keys: Key combination string (e.g., "ctrl+b", "Return")

        Returns:
            True if successful
        """
        try:
            import subprocess
            import shutil

            if shutil.which("xdotool"):
                subprocess.run(
                    ["xdotool", "key", "--clearmodifiers", keys],
                    check=True,
                    capture_output=True
                )
                return True
            else:
                debug_print("[CMD] xdotool not available for keystroke simulation")
                return False
        except Exception as e:
            debug_print(f"[CMD] Keystroke error: {e}")
            return False
