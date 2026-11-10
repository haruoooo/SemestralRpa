from datetime import datetime
from zoneinfo import ZoneInfo

SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def nowLocal() -> datetime:
    """Current time in São Paulo. Flows receive it by injection so tests can freeze the clock."""
    return datetime.now(SAO_PAULO)
