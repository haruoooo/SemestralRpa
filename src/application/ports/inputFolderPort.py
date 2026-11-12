from pathlib import Path
from typing import Protocol


class InputFolderPort(Protocol):
    """Folder where HR drops the spreadsheets (data/input/)."""

    def ensureExists(self) -> bool:
        """Creates the folder when missing (EX01). Returns True if it had to be created."""
        ...

    def listPending(self) -> list[Path]: ...

    def moveTo(self, path: Path, destination: str) -> Path:
        """destination: "processed", "rejected" or "rejected/duplicates". Never overwrites an existing file."""
        ...
