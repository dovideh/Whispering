#!/usr/bin/env python3
"""
Voice Commands Configuration Loader
Loads voice command definitions from config/voice_commands.yaml
"""

import yaml
from pathlib import Path
from typing import Dict, List, Optional


class VoiceCommandsConfig:
    """Loads and provides access to voice command definitions."""

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "voice_commands.yaml"
        self.config_path = Path(config_path)
        self.config = self._load_config()

    def _load_config(self) -> dict:
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            print(f"Voice commands config not found: {self.config_path}")
            return {"commands": {}, "detection_mode": "isolation", "prefix_word": "command"}

        with open(self.config_path, 'r') as f:
            data = yaml.safe_load(f)
            return data if data else {"commands": {}, "detection_mode": "isolation", "prefix_word": "command"}

    @property
    def detection_mode(self) -> str:
        """Get detection mode: 'isolation' or 'prefix'."""
        return self.config.get("detection_mode", "isolation")

    @property
    def prefix_word(self) -> str:
        """Get prefix word for prefix detection mode."""
        return self.config.get("prefix_word", "command")

    def get_commands(self) -> Dict:
        """Get all command definitions."""
        return self.config.get("commands", {})

    def build_trigger_map(self, language: str = None) -> Dict[str, dict]:
        """
        Build a flat lookup from trigger phrase -> command info.

        Args:
            language: Language code to filter triggers (e.g., 'en', 'he').
                      If None, includes triggers from all languages.

        Returns:
            Dict mapping lowercase trigger phrase -> {
                'command_id': str,
                'action': str,
                'insert': str or None,
                'format': str or None,
            }
        """
        trigger_map = {}
        commands = self.get_commands()

        for cmd_id, cmd_def in commands.items():
            triggers = cmd_def.get("triggers", {})
            action = cmd_def.get("action", "")
            insert = cmd_def.get("insert")
            fmt = cmd_def.get("format")

            # Collect trigger phrases for the specified language or all languages
            phrases = []
            if language and language in triggers:
                phrases = triggers[language]
            elif language is None:
                for lang_phrases in triggers.values():
                    phrases.extend(lang_phrases)
            else:
                # Language not found in triggers — try 'en' as fallback
                phrases = triggers.get("en", [])

            for phrase in phrases:
                trigger_map[phrase.lower().strip()] = {
                    "command_id": cmd_id,
                    "action": action,
                    "insert": insert,
                    "format": fmt,
                }

        return trigger_map


def load_voice_commands_config() -> Optional[VoiceCommandsConfig]:
    """
    Load voice commands configuration, returning None if not available.

    Returns:
        VoiceCommandsConfig instance or None
    """
    try:
        config = VoiceCommandsConfig()
        commands = config.get_commands()
        if not commands:
            print("Voice commands config loaded but contains no commands")
            return None
        return config
    except Exception as e:
        print(f"Error loading voice commands config: {e}")
        return None
