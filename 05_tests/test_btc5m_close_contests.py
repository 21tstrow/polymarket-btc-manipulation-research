from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "01_scripts" / "analyze_btc5m_close_contests.py"
SPEC = importlib.util.spec_from_file_location("analyze_btc5m_close_contests", SCRIPT_PATH)
assert SPEC is not None
close = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(close)


def event(
    start_epoch: int,
    *,
    slug_prefix: str = "btc-updown-5m",
    series_slug: str = "btc-up-or-down-5m",
    duration: int = 300,
    outcomes: str = '["Up", "Down"]',
    final_price: float | None = 101.0,
) -> dict:
    slug = f"{slug_prefix}-{start_epoch}"
    metadata = {"priceToBeat": 100.0}
    if final_price is not None:
        metadata["finalPrice"] = final_price
    return {
        "slug": slug,
        "seriesSlug": series_slug,
        "closed": True,
        "startTime": close.utc(start_epoch),
        "endDate": close.utc(start_epoch + duration),
        "eventMetadata": metadata,
        "series": [{"slug": series_slug, "recurrence": "5m"}],
        "markets": [
            {
                "slug": slug,
                "conditionId": "0xabc",
                "outcomes": outcomes,
                "eventStartTime": close.utc(start_epoch),
                "endDate": close.utc(start_epoch + duration),
                "volumeNum": 123.0,
            }
        ],
    }


def test_5m_slug_generation_and_300s_cadence(tmp_path: Path) -> None:
    assert close.slug_for_start(300) == "btc-updown-5m-300"
    starts = close.market_start_range({0: 100.0, 300: 101.0, 600: 102.0}, tmp_path)
    assert starts == [0, 300]


def test_gamma_5m_validation_accepts_valid_event() -> None:
    assert close.validate_5m_event(event(300), 300) == []


def test_gamma_validation_rejects_15m_series_and_duration() -> None:
    errors = close.validate_5m_event(
        event(900, slug_prefix="btc-updown-15m", series_slug="btc-up-or-down-15m", duration=900),
        900,
    )

    assert any("event slug" in error for error in errors)
    assert any("non-5m series" in error or "missing expected series" in error for error in errors)
    assert any("exact 300s" in error for error in errors)


def test_gamma_validation_rejects_malformed_outcomes() -> None:
    errors = close.validate_5m_event(event(300, outcomes="not-json"), 300)

    assert any("unexpected market outcomes" in error for error in errors)


def test_market_start_range_unions_rtds_cadence_with_cache(tmp_path: Path) -> None:
    cached_slug = close.slug_for_start(900)
    gamma_dir = tmp_path / "gamma"
    gamma_dir.mkdir()
    (gamma_dir / f"{cached_slug}.json").write_text("null\n", encoding="utf-8")

    starts = close.market_start_range({0: 100.0, 300: 101.0, 600: 102.0}, tmp_path)

    assert starts == [0, 300, 900]


def test_market_start_range_cache_only_uses_cached_slots(tmp_path: Path) -> None:
    cached_slug = close.slug_for_start(900)
    gamma_dir = tmp_path / "gamma"
    gamma_dir.mkdir()
    (gamma_dir / f"{cached_slug}.json").write_text("null\n", encoding="utf-8")

    starts = close.market_start_range(
        {0: 100.0, 300: 101.0, 600: 102.0},
        tmp_path,
        cache_only_market_starts=True,
    )

    assert starts == [900]


def test_build_market_rows_emits_only_5m_product_rows(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    gamma_dir = cache_dir / "gamma"
    gamma_dir.mkdir(parents=True)
    start_epoch = 300
    slug = close.slug_for_start(start_epoch)
    (gamma_dir / f"{slug}.json").write_text(json.dumps(event(start_epoch)), encoding="utf-8")

    rows, validation = close.build_market_rows(
        {300: 100.0, 360: 100.0, 570: 100.0, 585: 100.0, 590: 100.0, 600: 101.0, 615: 100.5, 660: 100.4, 900: 100.3},
        cache_dir=cache_dir,
        max_price_lag_seconds=0,
        allow_future_price_match=False,
        allow_rtds_final_fallback=False,
        fetch_missing=False,
    )

    assert len(rows) == 1
    assert validation[0]["status"] == "ok"
    assert rows[0]["market_timeframe"] == "5m"
    assert rows[0]["market_duration_seconds"] == 300
    assert rows[0]["series_slug"] == "btc-up-or-down-5m"
    assert rows[0]["slug"].startswith("btc-updown-5m-")
    assert rows[0]["prior_risk_lookback_seconds"] == 60


def test_build_market_rows_uses_named_prior_risk_lookback(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    gamma_dir = cache_dir / "gamma"
    gamma_dir.mkdir(parents=True)
    start_epoch = 300
    slug = close.slug_for_start(start_epoch)
    (gamma_dir / f"{slug}.json").write_text(json.dumps(event(start_epoch)), encoding="utf-8")

    rows, _ = close.build_market_rows(
        {300: 100.0, 540: 99.9, 570: 100.0, 600: 101.0, 660: 100.4, 900: 100.3},
        cache_dir=cache_dir,
        max_price_lag_seconds=0,
        allow_future_price_match=False,
        allow_rtds_final_fallback=False,
        fetch_missing=False,
        prior_risk_lookback_seconds=30,
    )

    assert rows[0]["prior_risk_lookback_seconds"] == 30
    assert rows[0]["prior_risk_margin_bps_abs"] == rows[0]["margin_minus_30s_bps_abs"]


def test_directional_summary_reports_configured_prior_risk_lookback() -> None:
    summary = close.summarize_directional_filters([], prior_risk_lookback_seconds=30)

    assert summary[0]["prior_risk_lookback_seconds"] == 30


def test_default_paths_do_not_point_at_15m_caches() -> None:
    assert "btc5m" in str(close.DEFAULT_CACHE_DIR)
    assert "btc5m" in str(close.DEFAULT_OUT_DIR)
    assert "btc15m" not in str(close.DEFAULT_CACHE_DIR)
    assert close.DEFAULT_OUT_DIR.relative_to(ROOT / "02_exports") != Path("close_contests")
