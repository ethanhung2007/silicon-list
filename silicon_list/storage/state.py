import json
from pathlib import Path
from dataclasses import asdict
import logging
from silicon_list.models import Listing

logger = logging.getLogger(__name__)

class StateManager:
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.seen_keys: set[str] = set()

    def load(self):
        """Loads seen keys from the state file. Tolerates missing or corrupted files."""
        if not self.file_path.exists():
            return
        
        try:
            with open(self.file_path, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    self.seen_keys = set(data)
                else:
                    logger.warning("Seen file is corrupted (not a list), reinitializing.")
                    self.seen_keys = set()
        except json.JSONDecodeError:
            logger.warning("Seen file is corrupted (invalid JSON), reinitializing.")
            self.seen_keys = set()
        except Exception as e:
            logger.error(f"Error reading seen file: {e}")
            self.seen_keys = set()

    def save(self):
        """Saves seen keys to the state file."""
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.file_path, "w") as f:
                json.dump(list(self.seen_keys), f, indent=4)
        except Exception as e:
            logger.error(f"Error saving seen file: {e}")

    def add(self, key: str):
        self.seen_keys.add(key)

    def is_seen(self, key: str) -> bool:
        return key in self.seen_keys
