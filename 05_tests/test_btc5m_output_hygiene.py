from __future__ import annotations

import csv
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_old_15m_entrypoints_fail_fast(capsys) -> None:
    for filename in (
        "analyze_btc15m_close_contests.py",
        "analyze_btc15m_underlying_volume.py",
        "analyze_btc15m_resolution_pressure.py",
    ):
        module = load_script(filename, ROOT / "01_scripts" / filename)
        assert module.main() == 2
        assert "5m-only" in capsys.readouterr().err


def test_output_hygiene_rejects_15m_slug_in_written_rows(tmp_path: Path) -> None:
    underlying = load_script(
        "analyze_btc5m_underlying_volume",
        ROOT / "01_scripts" / "analyze_btc5m_underlying_volume.py",
    )
    path = tmp_path / "rows.csv"
    rows = [
        {
            "market_timeframe": "5m",
            "market_duration_seconds": 300,
            "series_slug": "btc-up-or-down-5m",
            "slug_prefix": "btc-updown-5m",
            "slug": "btc-updown-5m-300",
            "condition_id": "0xabc",
        }
    ]
    underlying.write_csv(path, rows)

    written = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    assert all(row["market_timeframe"] == "5m" for row in written)
    assert all(row["market_duration_seconds"] == "300" for row in written)
    assert all(not row["slug"].startswith("btc-updown-15m-") for row in written)
