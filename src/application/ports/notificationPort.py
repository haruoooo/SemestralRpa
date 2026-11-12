from typing import Protocol

from src.domain.agenda import OutgoingEmail


class NotificationPort(Protocol):
    channel: str

    def send(self, email: OutgoingEmail) -> None:
        """Raises NotificationUnavailableError (retryable) or NotificationRejectedError (bad recipient)."""
        ...
