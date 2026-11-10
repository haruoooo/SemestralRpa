"""Retry with exponential backoff for transient failures (EX06, EX08, EX09)."""

from collections.abc import Callable
from typing import TypeVar

from tenacity import RetryCallState, Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.infrastructure.robotLogger import RunLogger

ResultType = TypeVar("ResultType")


def callWithRetry(
    operation: Callable[[], ResultType],
    *,
    retryOn: tuple[type[Exception], ...],
    attempts: int,
    baseSeconds: float,
    logger: RunLogger,
    step: str,
    description: str,
) -> ResultType:
    """Runs the operation, retrying only the given exception types. The last exception is re-raised."""

    def logRetry(state: RetryCallState) -> None:
        error = state.outcome.exception() if state.outcome else None
        logger.warning(
            step,
            "RetryScheduled",
            f"{description} failed (attempt {state.attempt_number}/{attempts}): {type(error).__name__}: {error}",
        )

    retrying = Retrying(
        retry=retry_if_exception_type(retryOn),
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=baseSeconds, max=baseSeconds * 4) if baseSeconds > 0 else (lambda _: 0),
        before_sleep=logRetry,
        reraise=True,
    )
    return retrying(operation)
