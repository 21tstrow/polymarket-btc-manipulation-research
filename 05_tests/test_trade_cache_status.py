from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "01_scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def load_script(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


collect15 = load_script("collect_btc15m_updown_data", ROOT / "01_scripts" / "collect_btc15m_updown_data.py")
close5 = load_script("analyze_btc5m_close_contests_for_cache_status", ROOT / "01_scripts" / "analyze_btc5m_close_contests.py")


def test_btc15m_missing_trade_cache_is_not_ok(tmp_path) -> None:
    args = argparse.Namespace(
        fetch_missing=False,
        sleep_seconds=0.0,
        timeout_seconds=1.0,
        request_attempts=1,
        retry_base_sleep=0.0,
        retry_max_sleep=0.0,
        max_trade_offset=500,
    )
    summary, pages = collect15.fetch_trade_pages(
        {"slug": "btc-up-or-down-15m-test", "condition_id": "0xc1"},
        tmp_path / "cache",
        args,
    )

    assert summary["trade_fetch_status"] == "missing_cache_at_offset_0"
    assert summary["trade_pages"] == 1
    assert pages[0]["cache_status"] == "missing_cache"
    assert summary["trade_raw_count"] == 0


def test_btc5m_missing_trade_cache_is_not_ok(tmp_path) -> None:
    trades, duplicates, raw_count, status = close5.fetch_late_trades(
        "0xc1",
        1000,
        tmp_path / "cache",
        fetch_missing=False,
    )

    assert status == "missing_cache_at_offset_0"
    assert trades == []
    assert duplicates == 0
    assert raw_count == 0
