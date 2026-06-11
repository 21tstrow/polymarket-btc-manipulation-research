from __future__ import annotations

from pathlib import Path


MARKET_TIMEFRAME = "5m"
MARKET_DURATION_SECONDS = 300
SLUG_PREFIX = "btc-updown-5m"
SERIES_SLUG = "btc-up-or-down-5m"

CORE_WINDOWS = (5, 10, 15, 30)
SENSITIVITY_WINDOWS = (60,)
WINDOWS = (*CORE_WINDOWS, *SENSITIVITY_WINDOWS)
POST_CLOSE_REVERSION_HORIZONS = (15, 60, 300)
NEXT_MARKET_SENSITIVITY_HORIZONS = (300,)

DEFAULT_MATCHED_FLAT_MARGIN_GRID = (5.0, 10.0, 20.0)
DEFAULT_MATCH_FILTERS = ("margin_only", "margin_plus_prior_30s_momentum")
DEFAULT_CONTROL_METHODS = ("nonoverlap", "anchor_points", "mid_window")
DEFAULT_ANCHOR_OFFSETS_SECONDS = (240, 180, 120, 60)
DEFAULT_MID_WINDOW_OFFSETS_SECONDS = (200, 150, 100)
DEFAULT_PRIOR_MOMENTUM_LOOKBACK_SECONDS = 30
DEFAULT_MAX_PRIOR_MOMENTUM_BPS = 10.0
DEFAULT_PRIOR_RISK_LOOKBACK_SECONDS = 60

DEFAULT_RTDS_DIR = Path("03_data_cache/chainlink_btc_usd")
DEFAULT_CLOSE_CACHE_DIR = Path("03_data_cache/polymarket_btc5m_close_contests_cache")
DEFAULT_UNDERLYING_CACHE_DIR = Path("03_data_cache/btc5m_underlying_volume_cache")
DEFAULT_CLOSE_OUT_DIR = Path("02_exports/btc5m_close_contests")
DEFAULT_UNDERLYING_OUT_DIR = Path("02_exports/btc5m_underlying_volume")
DEFAULT_PRESSURE_OUT_DIR = Path("02_exports/btc5m_resolution_pressure")

PRODUCT_FIELDS = (
    "market_timeframe",
    "market_duration_seconds",
    "series_slug",
    "slug_prefix",
)
PRODUCT_VALUES = {
    "market_timeframe": MARKET_TIMEFRAME,
    "market_duration_seconds": str(MARKET_DURATION_SECONDS),
    "series_slug": SERIES_SLUG,
    "slug_prefix": SLUG_PREFIX,
}


def slug_for_start(start_epoch: int) -> str:
    return f"{SLUG_PREFIX}-{start_epoch}"


PRODUCTS: dict[str, dict[str, str | int]] = {
    "5m": {
        "market_timeframe": MARKET_TIMEFRAME,
        "market_duration_seconds": MARKET_DURATION_SECONDS,
        "series_slug": SERIES_SLUG,
        "slug_prefix": SLUG_PREFIX,
    },
    "15m": {
        "market_timeframe": "15m",
        "market_duration_seconds": 900,
        "series_slug": "btc-up-or-down-15m",
        "slug_prefix": "btc-updown-15m",
    },
}


def product_fields(timeframe: str = "5m") -> dict[str, str | int]:
    if timeframe not in PRODUCTS:
        raise ValueError(f"unknown market timeframe {timeframe!r}; expected one of {sorted(PRODUCTS)}")
    return dict(PRODUCTS[timeframe])


def validate_product_row(row: dict, *, context: str = "row") -> None:
    for field, expected in PRODUCT_VALUES.items():
        actual = row.get(field)
        if actual is None or str(actual) == "":
            raise ValueError(f"{context} missing required 5m product field {field}")
        if str(actual) != expected:
            raise ValueError(
                f"{context} has non-5m product field {field}={actual!r}; expected {expected!r}"
            )

    slug = str(row.get("slug") or "")
    if slug and not slug.startswith(f"{SLUG_PREFIX}-"):
        raise ValueError(f"{context} has non-5m slug {slug!r}")


def validate_product_rows(rows: list[dict], *, context: str) -> None:
    for index, row in enumerate(rows, start=1):
        validate_product_row(row, context=f"{context} row {index}")
