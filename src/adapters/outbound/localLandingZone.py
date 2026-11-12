"""Big Data landing zone on the local disk (or a mounted/synced folder). JSON, UTF-8."""

import json
from pathlib import Path


class LocalLandingZone:
    def __init__(self, root: Path):
        self._root = root

    def write(self, dataset: str, fileName: str, payload: dict) -> str:
        folder = self._root / dataset
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / fileName
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)  # Atomic: the Big Data pipeline never reads a half-written file
        return str(target)
