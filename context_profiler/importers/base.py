"""Importer contracts for adding new agent harnesses."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ProfileImporter(Protocol):
    """A harness importer converts native telemetry into normalized JSONL events."""

    source: str

    def import_latest(self, limit: int = 5) -> list[Path]:
        """Import the most recent native session records for this source."""

