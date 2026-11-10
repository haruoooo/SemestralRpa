"""On-site assignment entity, as returned by the product API (GET /assignments)."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Assignment:
    assignmentId: str
    employeeId: str
    teamName: str
    lineNumber: int
    date: str
    entryWindow: str
    allowedEntryWindows: list[str] = field(default_factory=list)
    name: str = ""
    email: str = ""
    boardingStation: str = ""
    suggestedDepartureTime: str = ""
    predictedCrowding: str = ""

    @classmethod
    def fromApi(cls, payload: dict) -> "Assignment":
        known = {name for name in cls.__dataclass_fields__}
        return cls(**{key: value for key, value in payload.items() if key in known})
