#!/usr/bin/env python3
"""
Session Logger Module
Handles comprehensive logging of recording sessions with crash recovery
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class SessionLogger:
    """
    Handles logging of recording sessions with JSONL format and crash recovery.
    """

    def __init__(self, log_dir: str = "logs", max_file_size_mb: int = 5):
        """
        Initialize session logger.

        Args:
            log_dir: Base directory for logs
            max_file_size_mb: Maximum file size before rollover
        """
        self.log_dir = Path(log_dir)
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024
        self.current_request_id: Optional[str] = None
        self.current_temp_file: Optional[Path] = None
        self.session_start_time: Optional[datetime] = None
        self.current_file_size = 0

        # Ensure log directory exists
        self.log_dir.mkdir(exist_ok=True)

    def get_next_request_id(self) -> str:
        """
        Generate next request ID in 2YMMDDNNNN format.

        Returns:
            Request ID string
        """
        now = datetime.now()
        year_short = str(now.year)[2:]  # Last 2 digits
        month = f"{now.month:02d}"
        day = f"{now.day:02d}"

        # Create today's log directory
        today_dir = self.log_dir / year_short / month / day
        today_dir.mkdir(parents=True, exist_ok=True)

        # Find existing files for today
        existing_files = list(today_dir.glob("*.jsonl"))
        existing_count = len(existing_files)

        # Generate new ID
        request_id = f"{year_short}{month}{day}{existing_count + 1:04d}"
        return request_id

    def start_session(self, config: Dict) -> str:
        """
        Start a new logging session.

        Args:
            config: Configuration dictionary for the session

        Returns:
            Request ID for the session
        """
        self.current_request_id = self.get_next_request_id()
        self.session_start_time = datetime.now()

        # Create temp file path
        now = datetime.now()
        year_short = str(now.year)[2:]
        month = f"{now.month:02d}"
        day = f"{now.day:02d}"
        
        temp_dir = self.log_dir / year_short / month / day
        self.current_temp_file = temp_dir / f".temp_{self.current_request_id}.jsonl"
        self.current_file_size = 0

        # Create initial session entry
        session_entry = {
            "request_id": self.current_request_id,
            "session_start": self.session_start_time.isoformat() + "Z",
            "session_end": None,
            "duration_seconds": None,
            "config": config,
            "outputs": {
                "whisper_text": "",
                "ai_text": "",
                "translation_text": ""
            },
            "stop_reason": None
        }

        # Write initial entry to temp file
        self._write_to_temp_file(session_entry)

        return self.current_request_id

    def update_session(self, outputs: Dict[str, str]):
        """
        Update the current session with new outputs.

        Args:
            outputs: Dictionary with current outputs
        """
        if not self.current_temp_file or not self.current_request_id:
            return

        # Update session entry
        session_entry = {
            "request_id": self.current_request_id,
            "session_start": self.session_start_time.isoformat() + "Z",
            "session_end": None,
            "duration_seconds": None,
            "config": None,  # Don't repeat config in updates
            "outputs": outputs,
            "stop_reason": None
        }

        self._write_to_temp_file(session_entry)

    def finalize_session(self, stop_reason: str = "manual") -> Optional[Path]:
        """
        Finalize the current session and move temp file to permanent location.

        Args:
            stop_reason: Reason for stopping ("manual", "auto", "error", "unexpected")

        Returns:
            Path to final log file, or None if no active session
        """
        if not self.current_temp_file or not self.current_request_id:
            return None

        # Calculate duration
        session_end_time = datetime.now()
        duration_seconds = (session_end_time - self.session_start_time).total_seconds()

        # Create final session entry
        session_entry = {
            "request_id": self.current_request_id,
            "session_start": self.session_start_time.isoformat() + "Z",
            "session_end": session_end_time.isoformat() + "Z",
            "duration_seconds": duration_seconds,
            "config": None,
            "outputs": None,
            "stop_reason": stop_reason
        }

        # Write final entry to temp file
        self._write_to_temp_file(session_entry)

        # Create final file path
        final_file = self.current_temp_file.parent / f"{self.current_request_id}.jsonl"

        # Move temp file to final location
        if self.current_temp_file.exists():
            self.current_temp_file.rename(final_file)

        # Reset state
        self.current_request_id = None
        self.current_temp_file = None
        self.session_start_time = None
        self.current_file_size = 0

        return final_file

    def _write_to_temp_file(self, session_entry: Dict):
        """
        Write session entry to temp file with size checking.

        Args:
            session_entry: Session data to write
        """
        if not self.current_temp_file:
            return

        # Convert to pretty-printed JSON
        json_line = json.dumps(session_entry, indent=2, ensure_ascii=False) + "\n"
        
        # Check if this would exceed file size limit
        entry_size = len(json_line.encode('utf-8'))
        if self.current_file_size + entry_size > self.max_file_size_bytes:
            # File would be too large, finalize current and start new
            self._handle_file_rollover()
            # Restart session with new request ID
            self.current_request_id = self.get_next_request_id()
            # Update the entry with new request ID
            session_entry["request_id"] = self.current_request_id
            json_line = json.dumps(session_entry, indent=2, ensure_ascii=False) + "\n"

        # Write to temp file
        with open(self.current_temp_file, 'a', encoding='utf-8') as f:
            f.write(json_line)

        self.current_file_size += entry_size

    def _handle_file_rollover(self):
        """
        Handle file size limit by finalizing current and preparing for new file.
        """
        if self.current_temp_file and self.current_temp_file.exists():
            # Finalize current session with auto-stop reason
            final_file = self.current_temp_file.parent / f"{self.current_request_id}.jsonl"
            self.current_temp_file.rename(final_file)

    def scan_for_temp_files(self) -> List[Tuple[Path, str]]:
        """
        Scan for temporary log files (crashed sessions).

        Returns:
            List of tuples (temp_file_path, formatted_timestamp)
        """
        temp_files = []
        
        # Recursively scan for temp files
        for temp_file in self.log_dir.rglob(".temp_*.jsonl"):
            try:
                # Extract timestamp from filename
                filename = temp_file.name
                request_id = filename.replace(".temp_", "").replace(".jsonl", "")
                
                # Parse date from request ID (2YMMDDNNNN format)
                if len(request_id) >= 6:
                    year_short = request_id[:2]
                    month = request_id[2:4]
                    day = request_id[4:6]
                    
                    # Format timestamp
                    timestamp = f"20{year_short}-{month}-{day}"
                    temp_files.append((temp_file, timestamp))
                    
            except Exception as e:
                print(f"Error parsing temp file {temp_file}: {e}")
                continue

        return sorted(temp_files, key=lambda x: x[0].stat().st_mtime, reverse=True)

    def recover_session(self, temp_file: Path) -> Optional[Path]:
        """
        Recover a crashed session by finalizing its temp file.

        Args:
            temp_file: Path to temp file

        Returns:
            Path to final log file, or None if recovery failed
        """
        try:
            if not temp_file.exists():
                return None

            # Extract request ID from filename
            filename = temp_file.name
            request_id = filename.replace(".temp_", "").replace(".jsonl", "")
            
            # Create final file path
            final_file = temp_file.parent / f"{request_id}.jsonl"
            
            # Move temp file to final location
            temp_file.rename(final_file)
            
            return final_file
            
        except Exception as e:
            print(f"Error recovering session {temp_file}: {e}")
            return None

    def discard_session(self, temp_file: Path) -> bool:
        """
        Discard a crashed session by deleting its temp file.

        Args:
            temp_file: Path to temp file

        Returns:
            True if discarded successfully, False otherwise
        """
        try:
            if temp_file.exists():
                temp_file.unlink()
            return True
        except Exception as e:
            print(f"Error discarding session {temp_file}: {e}")
            return False

    def get_current_log_file(self) -> Optional[str]:
        """
        Get the current log file path for display.

        Returns:
            Current log file path or None if no active session
        """
        if self.current_temp_file:
            return str(self.current_temp_file.name.replace(".temp_", ""))
        return None


if __name__ == "__main__":
    """Test the session logger."""
    import tempfile
    import shutil

    # Create temporary log directory for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        logger = SessionLogger(log_dir=temp_dir, max_file_size_mb=1)
        
        print("Testing Session Logger...")
        
        # Test starting a session
        test_config = {
            "model": "large-v3",
            "vad_enabled": True,
            "ai_enabled": True,
            "ai_persona": "Q&A"
        }
        
        request_id = logger.start_session(test_config)
        print(f"Started session: {request_id}")
        
        # Test updating session
        outputs = {
            "whisper_text": "Hello world",
            "ai_text": "Hello! How can I help you?",
            "translation_text": ""
        }
        
        logger.update_session(outputs)
        print("Updated session with outputs")
        
        # Test finalizing session
        final_file = logger.finalize_session("manual")
        print(f"Finalized session: {final_file}")
        
        # Test scanning for temp files
        temp_files = logger.scan_for_temp_files()
        print(f"Found temp files: {len(temp_files)}")
        
        print("✓ Session logger test passed")
