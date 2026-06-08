#!/usr/bin/env python3
from __future__ import annotations

import sys


def main() -> int:
    print(
        "error: this repo is now BTC Up/Down 5m-only. "
        "Use 01_scripts/analyze_btc5m_underlying_volume.py.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
