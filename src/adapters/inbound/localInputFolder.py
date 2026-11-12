"""HR drop folder on the local disk: data/input/ with processed/ and rejected/ subfolders."""

import shutil
from pathlib import Path

from src.infrastructure.timeProvider import nowLocal


class LocalInputFolder:
    def __init__(self, root: Path):
        self._root = root

    def ensureExists(self) -> bool:
        created = not self._root.exists()
        self._root.mkdir(parents=True, exist_ok=True)
        return created

    def listPending(self) -> list[Path]:
        # Every regular file is a candidate: a .csv or a renamed file must be rejected, not silently ignored (EX02)
        return sorted(
            path for path in self._root.iterdir()
            if path.is_file() and not path.name.startswith(("~$", ".")) and path.name != ".gitkeep"
        )

    def moveTo(self, path: Path, destination: str) -> Path:
        folder = self._root / destination
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / path.name
        if target.exists():
            target = folder / f"{path.stem}{nowLocal().strftime('%Y%m%d%H%M%S')}{path.suffix}"
        return Path(shutil.move(str(path), str(target)))
