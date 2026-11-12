from typing import Protocol


class LandingZonePort(Protocol):
    """Big Data landing folder (chegada/). Receives pseudonymized batches only."""

    def write(self, dataset: str, fileName: str, payload: dict) -> str:
        """Writes the batch and returns its location."""
        ...
