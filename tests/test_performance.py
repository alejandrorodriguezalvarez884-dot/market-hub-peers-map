"""Returns from daily closes, and when a visit makes the service ask Yahoo again. No network: the
closes are written here and the clock is set by the test."""

from datetime import date, datetime, timedelta, timezone

import pytest

from peermap.performance import Performance, PerformanceUnavailable, last_close, market_open, returns

UTC = timezone.utc


def sessions(n: int, last: date = date(2026, 10, 7)) -> list[str]:
    """The last ``n`` weekdays up to ``last``, oldest first."""
    days, d = [], last
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d.isoformat())
        d -= timedelta(days=1)
    return days[::-1]


def test_returns_count_sessions_back_as_the_portal_does():
    dates = sessions(300)
    closes = [100.0 + i for i in range(300)]  # 100 ... 399
    day, week, month, ytd, year = returns(dates, closes)
    assert day == round(399 / 398 - 1, 4)
    assert week == round(399 / 394 - 1, 4)  # 5 sessions back
    assert month == round(399 / 378 - 1, 4)  # 21 sessions back
    assert year == round(399 / 147 - 1, 4)  # 252 sessions back
    last_of_2025 = max(i for i, d in enumerate(dates) if d < "2026")
    assert ytd == round(399 / closes[last_of_2025] - 1, 4)


def test_a_short_history_leaves_the_long_spans_empty():
    dates = sessions(10)
    assert returns(dates, [10.0] * 9 + [11.0]) == [0.1, 0.1, None, None, None]
    # Listed this year: there is no close of the year before to count from.
    assert returns(sessions(30), [10.0] * 30)[3] is None


def test_the_market_s_hours_in_new_york():
    assert market_open(datetime(2026, 10, 7, 15, 0, tzinfo=UTC))  # Wednesday 11:00 in New York
    assert not market_open(datetime(2026, 10, 7, 13, 0, tzinfo=UTC))  # 09:00, before the bell
    assert not market_open(datetime(2026, 10, 10, 15, 0, tzinfo=UTC))  # Saturday
    # Sunday night: the last close was Friday's.
    assert last_close(datetime(2026, 10, 11, 23, 0, tzinfo=UTC)).date() == date(2026, 10, 9)
    # Tuesday morning before the open: Monday's.
    assert last_close(datetime(2026, 10, 6, 12, 0, tzinfo=UTC)).date() == date(2026, 10, 5)


class Clock:
    def __init__(self, at: datetime):
        self.at = at

    def __call__(self) -> datetime:
        return self.at


def flat_closes(asked: list):
    def closes(tickers):
        asked.append(list(tickers))
        return {t: (sessions(30), [10.0] * 29 + [11.0]) for t in tickers if t != "GONE"}
    return closes


def test_a_visit_refreshes_stale_figures_and_only_those(store):
    clock, asked = Clock(datetime(2026, 10, 7, 15, 0, tzinfo=UTC)), []
    perf = Performance(store, ["AAPL", "MSFT", "KO"], closes=flat_closes(asked), ttl=900, now=clock, batch=2)
    assert perf.get() == {"as_of": None, "stale": True, "periods": ["1d", "1w", "1m", "ytd", "1y"], "returns": {}}
    doc = perf.refresh()
    assert asked == [["AAPL", "MSFT"], ["KO"]]  # in batches
    assert doc["stale"] is False and doc["returns"]["KO"][0] == 0.1 and doc["as_of"] == "2026-10-07T15:00:00+00:00"
    perf.refresh()
    assert len(asked) == 2  # fresh: Yahoo is not asked again
    clock.at += timedelta(minutes=20)
    assert perf.get()["stale"] is True
    perf.refresh()
    assert len(asked) == 4


def test_with_the_market_closed_the_figures_are_read_once_after_the_close(store):
    clock, asked = Clock(datetime(2026, 10, 7, 19, 0, tzinfo=UTC)), []  # Wednesday 15:00 in New York
    perf = Performance(store, ["AAPL"], closes=flat_closes(asked), ttl=900, now=clock)
    perf.refresh()
    clock.at = datetime(2026, 10, 7, 23, 0, tzinfo=UTC)  # 19:00: closed, and read before the close
    assert perf.get()["stale"] is True
    perf.refresh()
    clock.at = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)  # the night after: nothing new to read
    assert perf.get()["stale"] is False
    perf.refresh()
    assert len(asked) == 2


def test_another_instance_s_refresh_is_found_in_the_store(store):
    clock, asked = Clock(datetime(2026, 10, 7, 15, 0, tzinfo=UTC)), []
    first = Performance(store, ["AAPL"], closes=flat_closes(asked), now=clock)
    second = Performance(store, ["AAPL"], closes=flat_closes(asked), now=clock)
    assert second.get()["stale"] is True  # read before the first one refreshed
    first.refresh()
    assert second.refresh()["stale"] is False and len(asked) == 1


def test_two_visits_at_once_make_one_refresh_and_both_get_it(store):
    import threading

    started, go, asked = threading.Event(), threading.Event(), []

    def slow(tickers):
        asked.append(tickers)
        started.set()
        go.wait(5)
        return {t: (sessions(30), [10.0] * 29 + [11.0]) for t in tickers}

    perf = Performance(store, ["AAPL"], closes=slow, now=Clock(datetime(2026, 10, 7, 15, 0, tzinfo=UTC)))
    answers = []
    first = threading.Thread(target=lambda: answers.append(perf.refresh()))
    first.start()
    started.wait(5)
    second = threading.Thread(target=lambda: answers.append(perf.refresh()))
    second.start()
    go.set()
    first.join(5), second.join(5)
    assert len(asked) == 1 and len(answers) == 2
    assert all(a["stale"] is False and a["returns"]["AAPL"][0] == 0.1 for a in answers)


def test_a_company_yahoo_does_not_answer_for_keeps_its_last_figures(store):
    clock, asked = Clock(datetime(2026, 10, 7, 15, 0, tzinfo=UTC)), []
    Performance(store, ["GONE", "AAPL", "KO"], closes=lambda ts: {t: (sessions(30), [10.0] * 30) for t in ts}, now=clock).refresh()
    clock.at += timedelta(hours=1)
    doc = Performance(store, ["GONE", "AAPL", "KO"], closes=flat_closes(asked), now=clock).refresh()
    assert doc["returns"]["GONE"][0] == 0.0 and doc["returns"]["AAPL"][0] == 0.1


def test_when_yahoo_fails_nothing_is_kept_and_it_says_so(store):
    def broken(tickers):
        raise RuntimeError("https://query1.finance.yahoo.com/...")

    perf = Performance(store, ["AAPL", "KO"], closes=broken, now=Clock(datetime(2026, 10, 7, 15, 0, tzinfo=UTC)))
    with pytest.raises(PerformanceUnavailable):
        perf.refresh()
    assert store.get("performance") is None and perf.get()["stale"] is True
