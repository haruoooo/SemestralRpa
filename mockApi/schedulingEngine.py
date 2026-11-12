"""Reference scheduling heuristic used by the mock (the real engine lives in the product API).

Same idea as the group proposal: put each person in the entry window with the lowest predicted
crowding that still respects their restriction, and fill each team's days up to the demand.
Crowding here is a fixed curve around the morning peak; the real API uses the Big Data forecast.
"""

from collections import defaultdict
from datetime import datetime, timedelta
from math import ceil

TRAVEL_MINUTES = 55  # Fixed door-to-office estimate for the mock
CROWDING_ORDER = {"empty": 0, "moderate": 1, "full": 2, "critical": 3}


def _minutes(window: str) -> int:
    hours, minutes = window.split(":")
    return int(hours) * 60 + int(minutes)


def predictedCrowding(window: str) -> str:
    minutes = _minutes(window)
    if 450 <= minutes < 540:  # 07:30 to 09:00
        return "critical"
    if 420 <= minutes < 450 or 540 <= minutes < 600:
        return "full"
    if 360 <= minutes < 420 or 600 <= minutes < 660:
        return "moderate"
    return "empty"


def bestWindow(windows: list[str], latest: str | None) -> str:
    allowed = [window for window in windows if latest is None or _minutes(window) <= _minutes(latest)] or sorted(windows)[:1]
    return min(allowed, key=lambda window: (CROWDING_ORDER[predictedCrowding(window)], -_minutes(window)))


def departureTime(window: str) -> str:
    return (datetime.strptime(window, "%H:%M") - timedelta(minutes=TRAVEL_MINUTES)).strftime("%H:%M")


def buildAssignments(payload: dict, scheduleId: str) -> list[dict]:
    windows = payload["entryWindows"]
    employeesByTeam: dict[str, list[dict]] = defaultdict(list)
    for employee in payload["employees"]:
        employeesByTeam[employee["teamName"]].append(employee)

    assignments: list[dict] = []
    for team in payload["teams"]:
        members = employeesByTeam.get(team["teamName"], [])
        quota = {member["employeeId"]: max(1, ceil(member["monthlyOnSiteDays"] / 4)) for member in members}
        days: dict[str, list[dict]] = {item["date"]: [] for item in team["demand"]}
        demand = {item["date"]: item for item in team["demand"]}

        def candidates(day: str) -> list[dict]:
            return sorted(
                (
                    member for member in members
                    if quota[member["employeeId"]] > 0 and day not in member.get("unavailableDates", []) and member not in days[day]
                ),
                key=lambda member: -quota[member["employeeId"]],
            )

        # Pass 1: mandatory days first, each day up to its minimum
        for day in sorted(days, key=lambda item: (not demand[item]["mandatory"], item)):
            target = demand[day]["maxPeople"] if demand[day]["mandatory"] else demand[day]["minPeople"]
            for member in candidates(day)[: max(0, target - len(days[day]))]:
                days[day].append(member)
                quota[member["employeeId"]] -= 1
        # Pass 2: spread the remaining weekly quota on the emptiest days, never above the maximum
        for _ in range(5):
            for day in sorted(days, key=lambda item: len(days[item])):
                if len(days[day]) < demand[day]["maxPeople"]:
                    for member in candidates(day)[:1]:
                        days[day].append(member)
                        quota[member["employeeId"]] -= 1

        for day, people in sorted(days.items()):
            for member in people:
                window = bestWindow(windows, member.get("latestEntryWindow"))
                assignments.append(
                    {
                        "assignmentId": f"as-{scheduleId}-{member['employeeId']}-{day}",
                        "employeeId": member["employeeId"],
                        "name": member["name"],
                        "email": member["email"],
                        "teamName": member["teamName"],
                        "lineNumber": member["lineNumber"],
                        "boardingStation": member["boardingStation"],
                        "date": day,
                        "entryWindow": window,
                        "allowedEntryWindows": windows,
                        "suggestedDepartureTime": departureTime(window),
                        "predictedCrowding": predictedCrowding(window),
                    }
                )
    return assignments
