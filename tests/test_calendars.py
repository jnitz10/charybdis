from datetime import UTC, datetime

from charybdis.calendars import label_krx, label_nyse


def test_nyse_dst_change_uses_new_york_session_in_utc() -> None:
    assert label_nyse(datetime(2026, 3, 8, 16, 0, tzinfo=UTC)) == "weekend"
    assert (
        label_nyse(datetime(2026, 3, 9, 13, 29, 59, tzinfo=UTC))
        == "off-hours-weekday"
    )
    assert label_nyse(datetime(2026, 3, 9, 13, 30, tzinfo=UTC)) == "RTH"
    assert label_nyse(datetime(2026, 3, 6, 14, 30, tzinfo=UTC)) == "RTH"


def test_nyse_half_day_and_observed_independence_day() -> None:
    assert label_nyse(datetime(2026, 7, 3, 16, 0, tzinfo=UTC)) == "holiday"
    assert label_nyse(datetime(2026, 11, 27, 17, 59, tzinfo=UTC)) == "RTH"
    assert (
        label_nyse(datetime(2026, 11, 27, 18, 0, tzinfo=UTC))
        == "off-hours-weekday"
    )


def test_krx_holiday_and_regular_kst_session() -> None:
    assert label_krx(datetime(2026, 5, 5, 1, 0, tzinfo=UTC)) == "holiday"
    assert label_krx(datetime(2026, 5, 6, 0, 0, tzinfo=UTC)) == "RTH"
    assert (
        label_krx(datetime(2026, 5, 6, 6, 30, tzinfo=UTC))
        == "off-hours-weekday"
    )
