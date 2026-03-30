"""State persistence for dock position and expanded state."""

import json
import os

from .config import CONFIG_DIR, STATE_FILE, DEFAULT_MARGIN_TOP
from .logger import log


class StateManager:
    """Manages dock state persistence."""

    def __init__(self):
        self._margin_top = DEFAULT_MARGIN_TOP
        self._expanded = False

    def load(self) -> dict:
        """Load state from config file."""
        if not os.path.isfile(STATE_FILE):
            log.info("No state file, using defaults")
            return self._get_defaults()

        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
            self._margin_top = int(state.get("margin_top", DEFAULT_MARGIN_TOP))
            expanded = state.get("expanded")
            expanded_per_monitor = state.get("expanded_per_monitor", {})
            log.info(
                f"Loaded state: margin_top={self._margin_top}, expanded_per_monitor={expanded_per_monitor}"
            )
            return {
                "margin_top": self._margin_top,
                "expanded": expanded,
                "expanded_per_monitor": expanded_per_monitor,
            }
        except Exception as e:
            log.error(f"Failed to load state: {e}")
            return self._get_defaults()

    def save(self, margin_top: int, expanded):
        """Save state to config file."""
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            if isinstance(expanded, dict):
                state = {"margin_top": margin_top, "expanded_per_monitor": expanded}
            else:
                state = {"margin_top": margin_top, "expanded": expanded}
            with open(STATE_FILE, "w") as f:
                json.dump(state, f, indent=2)
            log.info(f"Saved state: margin_top={margin_top}, expanded={expanded}")
        except Exception as e:
            log.error(f"Failed to save state: {e}")

    def _get_defaults(self) -> dict:
        self._margin_top = DEFAULT_MARGIN_TOP
        self._expanded = False
        return {"margin_top": self._margin_top, "expanded": self._expanded}

    @property
    def margin_top(self) -> int:
        return self._margin_top

    @margin_top.setter
    def margin_top(self, value: int):
        self._margin_top = value

    @property
    def expanded(self) -> bool:
        return self._expanded

    @expanded.setter
    def expanded(self, value: bool):
        self._expanded = value
