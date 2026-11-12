"""Domain exceptions: every external failure is translated into one of these by the adapters."""


class RobotError(Exception):
    """Base class for known robot failures."""


class SourceUnavailableError(RobotError):
    """The line status source could not be reached (timeout, connection error, 403, 5xx). EX09."""


class SourceLayoutChangedError(RobotError):
    """The source answered, but its content no longer matches the expected layout. EX10."""


class ApiUnavailableError(RobotError):
    """The product API could not be reached (timeout, connection error, 5xx). EX06."""


class ApiRejectedError(RobotError):
    """The product API refused the payload (4xx). Not retried. EX07."""

    def __init__(self, message: str, statusCode: int, responseBody: str = ""):
        super().__init__(message)
        self.statusCode = statusCode
        self.responseBody = responseBody


class InvalidSpreadsheetError(RobotError):
    """The input file is corrupted or is not a .xlsx workbook. EX02."""
