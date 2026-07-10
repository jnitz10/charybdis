"""DST-safe exchange-session labels for NYSE and Korea Exchange timestamps."""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from typing import Literal
from zoneinfo import ZoneInfo

import exchange_calendars as exchange_calendars


SessionLabel = Literal["RTH", "off-hours-weekday", "weekend", "holiday"]
Exchange = Literal["XNYS", "XKRX"]

_TIMEZONES = {
    "XNYS": ZoneInfo("America/New_York"),
    "XKRX": ZoneInfo("Asia/Seoul"),
}


def label_nyse(timestamp: datetime) -> SessionLabel:
    return label_session(timestamp, "XNYS")


def label_krx(timestamp: datetime) -> SessionLabel:
    return label_session(timestamp, "XKRX")


def label_session(timestamp: datetime, exchange: Exchange) -> SessionLabel:
    """Label an aware timestamp using the exchange's local date and schedule."""

    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    try:
        timezone = _TIMEZONES[exchange]
    except KeyError as exc:
        raise ValueError(f"unsupported exchange {exchange!r}") from exc

    local_date = timestamp.astimezone(timezone).date()
    if local_date.weekday() >= 5:
        return "weekend"

    calendar = _calendar(exchange)
    session = local_date.isoformat()
    if not calendar.is_session(session):
        return "holiday"

    instant = timestamp.astimezone(UTC)
    opened = calendar.session_open(session).to_pydatetime()
    closed = calendar.session_close(session).to_pydatetime()
    if opened <= instant < closed:
        return "RTH"
    return "off-hours-weekday"


@lru_cache(maxsize=2)
def _calendar(exchange: Exchange):
    return exchange_calendars.get_calendar(exchange)
