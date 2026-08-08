"""Financial-safety end-to-end test: broker credentials must NEVER leak
through logs, the JSONL trade journal, or CLI stdout.

This is the single most important test in this batch. `SecretRegistry` +
`redact_text`/`redact_mapping` (see `adapters/logging/redaction.py`) are
meant to be the ONE chokepoint every log record and every journal record
passes through. This test proves that chokepoint actually holds end-to-end:

  1. Drives a full simulated `TradingSession` -- the same offline flow as
     `tests/e2e/test_offline_session.py` -- wired through the REAL
     `cli/wire.py` composition root with distinctive sentinel credentials.
  2. ALSO deliberately emits one adversarial log record and appends one
     adversarial journal record that DO contain the sentinel secrets. This
     is what makes the "nothing leaks" assertions below REAL assertions
     rather than trivial ones: nothing in the normal trading flow logs
     credentials in the first place (no code path ever touches them after
     `cli/wire.py` registers them), so without an adversarial probe, these
     checks would pass even if redaction were completely broken. The
     adversarial probe proves the chokepoint actively substitutes
     `***REDACTED***` -- not merely that nothing happened to trigger it.
  3. Reads the raw journal bytes with plain `open()`/`Path.read_bytes()`,
     NOT through `JsonlTradeLog.read()`, so a redacting reader could never
     mask a leak that is actually sitting on disk.
  4. Exercises `cli/report.py::print_summary` and checks its stdout too.

Root-logger state (the `RedactingFilter` `cli/wire.py` installs via
`logging_setup.configure()`) is reset around every test by the autouse
`_reset_root_logger` fixture in `tests/conftest.py` -- see that fixture's
docstring for why that matters here specifically.
"""
from __future__ import annotations

import io
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from botafuturo.adapters.logging.redaction import SecretRegistry, redact_text
from botafuturo.cli.report import print_summary, summarize
from botafuturo.cli.run import run_session
from botafuturo.cli.wire import build_paper_trading_session
from botafuturo.config.settings import Settings
from botafuturo.domain.models import Candle
from tests.fakes.market_data import FakeMarketData

_ASSET = "EURUSD"
_TIMEFRAME_S = 60
_T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
# Same proven bullish-crossover fixture as
# tests/e2e/test_offline_session.py (fast_period=2, slow_period=3 =>
# warmup_bars()==4): flat "10"x4 then "12", plus one trailing candle ("14")
# so the opened position's 60s expiry settles within this same finite
# stream -- this guarantees at least one real trade (and one real journal
# append) happens through the normal session flow, not just the
# adversarial probe.
_CLOSES = ["10", "10", "10", "10", "12", "14"]

_SENTINEL_EMAIL = "sentinel-user@example.com"
_SENTINEL_PASSWORD = "sentinel-Sup3rSecret!"
_REDACTED = "***REDACTED***"


def _candle(index: int, close: str) -> Candle:
    return Candle(
        asset=_ASSET,
        open_time=_T0 + timedelta(seconds=index * _TIMEFRAME_S),
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=Decimal("10"),
        timeframe_s=_TIMEFRAME_S,
    )


@pytest.fixture()
def sentinel_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.delenv("EXNOVA_EMAIL", raising=False)
    monkeypatch.delenv("EXNOVA_PASSWORD", raising=False)
    monkeypatch.setenv("EXNOVA_EMAIL", _SENTINEL_EMAIL)
    monkeypatch.setenv("EXNOVA_PASSWORD", _SENTINEL_PASSWORD)
    monkeypatch.setenv("SMA_FAST_PERIOD", "2")
    monkeypatch.setenv("SMA_SLOW_PERIOD", "3")
    return Settings(_env_file=None)


@pytest.fixture()
def log_capture():
    """A dedicated root-logger handler, independent of pytest's `caplog`.

    It is attached to the root logger's handler list AFTER
    `build_paper_trading_session` installs `logging_setup.configure()`'s
    redacting handler (see the test body), so `logging.Logger.callHandlers`
    always processes the redacting handler first and this handler observes
    each record's message/args AFTER `RedactingFilter` has already mutated
    them in place -- avoiding any ordering race with a leak.
    """
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    yield stream, handler
    logging.getLogger().removeHandler(handler)


@pytest.mark.e2e
def test_credentials_never_leak_through_logs_journal_or_stdout(
    sentinel_settings: Settings,
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    log_capture,
) -> None:
    stream, handler = log_capture
    candles = [_candle(i, close) for i, close in enumerate(_CLOSES)]
    market_data = FakeMarketData(candles=candles)

    wired = build_paper_trading_session(
        sentinel_settings, market_data, asset=_ASSET, journal_dir=tmp_path
    )
    logging.getLogger().addHandler(handler)

    processed = run_session(wired.session, market_data, _ASSET, _TIMEFRAME_S)
    assert processed == len(_CLOSES)

    # --- Adversarial probes: prove the chokepoint actively redacts. ---
    # NOTE: an earlier version of `RedactingFilter.filter()` ran
    # `redact_text` against the raw, UN-substituted `record.msg` template
    # (independently from `record.args`), so a template shaped like
    # `"password=%s"` had its OWN placeholder text matched and rewritten to
    # `"password=***REDACTED***"` before %-substitution ever happened,
    # leaving stray extra `%`-args and raising `TypeError: not all
    # arguments converted during string formatting` inside `emit()`
    # (silently swallowed by `logging`'s own error handling). That bug is
    # now fixed -- `filter()` redacts `record.getMessage()` (the FINAL,
    # fully-substituted message) instead -- and is covered by a dedicated
    # regression test in `tests/unit/test_redaction.py`. This test still
    # avoids a `password=%s`-shaped template because it targets
    # registered-secret-VALUE redaction specifically, not that key=value
    # regex interaction.
    logging.getLogger(__name__).warning(
        "login attempt credentials: %s / %s", _SENTINEL_EMAIL, _SENTINEL_PASSWORD
    )
    wired.trade_log.append(
        {
            "note": f"login attempt email={_SENTINEL_EMAIL} password={_SENTINEL_PASSWORD}",
            "ts": _T0.isoformat(),
        }
    )

    summary = summarize(wired.trade_log)
    assert summary.trade_count >= 1  # the normal session flow really traded
    print_summary(summary)

    # (a) captured log output -- covers both the normal session's own log
    # lines AND the adversarial probe above.
    log_text = stream.getvalue()
    assert log_text, "expected at least one log record to have been captured"
    assert _SENTINEL_EMAIL not in log_text
    assert _SENTINEL_PASSWORD not in log_text
    assert _REDACTED in log_text, (
        "expected the adversarial log record to show the redaction marker, "
        "proving active substitution -- not a silently dropped record"
    )

    # (b) raw journal file bytes -- read directly with Path.read_bytes(),
    # NOT through JsonlTradeLog.read(), so a redacting reader can never mask
    # a leak that is actually sitting on disk.
    journal_files = list(tmp_path.glob("*.jsonl"))
    assert len(journal_files) == 1
    raw_journal = journal_files[0].read_bytes()
    assert _SENTINEL_EMAIL.encode() not in raw_journal
    assert _SENTINEL_PASSWORD.encode() not in raw_journal
    assert _REDACTED.encode() in raw_journal, (
        "expected the adversarial journal record to show the redaction "
        "marker on disk, proving active substitution -- not a skipped write"
    )

    # (c) stdout from cli/report.py::print_summary
    captured = capsys.readouterr()
    assert _SENTINEL_EMAIL not in captured.out
    assert _SENTINEL_PASSWORD not in captured.out


def test_redact_text_strips_a_raw_secret_substring_outright() -> None:
    """Companion sanity check, isolated from all logging-handler plumbing:
    proves `redact_text` itself (the primitive the e2e test above relies
    on) actually strips a registered secret value.
    """
    registry = SecretRegistry()
    registry.register(_SENTINEL_PASSWORD)

    redacted = redact_text(f"password={_SENTINEL_PASSWORD}", registry)

    assert _SENTINEL_PASSWORD not in redacted
    assert _REDACTED in redacted
