from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "01_scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

SCRIPT_PATH = ROOT / "01_scripts" / "analyze_btc5m_copy_leader.py"
SPEC = importlib.util.spec_from_file_location("analyze_btc5m_copy_leader", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
cl = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cl)


LEADER = "0xleader"
FOL1 = "0xfollower1"
FOL2 = "0xfollower2"
FOLLOWERS = {FOL1, FOL2}


def test_match_events_leader_leads_followers() -> None:
    buys = [
        (100, LEADER, "Up"),
        (102, FOL1, "Up"),   # mirrors leader 2s later
        (103, FOL2, "Up"),   # mirrors leader 3s later
        (200, LEADER, "Up"),
        (201, FOL1, "Up"),
    ]
    lead, lag, same, f_ev, w_tr = cl.match_events(buys, FOLLOWERS, window=3)
    assert lead[(LEADER, FOL1)] == 2
    assert lead[(LEADER, FOL2)] == 1
    # leader never trails a follower; other followers may (fast vs slow mirrors)
    assert not any(w == LEADER for (w, _f) in lag)
    assert f_ev[FOL1] == 2 and f_ev[FOL2] == 1
    assert w_tr[LEADER] == 2


def test_match_events_outcome_must_match() -> None:
    buys = [(100, LEADER, "Down"), (101, FOL1, "Up")]
    lead, lag, same, _, _ = cl.match_events(buys, FOLLOWERS, window=3)
    assert not lead and not lag and not same


def test_match_events_market_maker_is_symmetric() -> None:
    mm = "0xmm"
    buys = [
        (99, mm, "Up"), (101, FOL1, "Up"), (103, mm, "Up"),
        (199, mm, "Up"), (201, FOL1, "Up"), (203, mm, "Up"),
    ]
    lead, lag, same, _, _ = cl.match_events(buys, FOLLOWERS, window=3)
    assert lead[(mm, FOL1)] == 2 and lag[(mm, FOL1)] == 2  # ratio 0.5


def test_match_events_same_second_counted_separately() -> None:
    buys = [(100, LEADER, "Up"), (100, FOL1, "Up")]
    lead, lag, same, _, _ = cl.match_events(buys, FOLLOWERS, window=3)
    assert not lead and not lag
    assert same[(LEADER, FOL1)] == 1


def test_match_events_window_respected() -> None:
    buys = [(95, LEADER, "Up"), (101, FOL1, "Up")]  # 6s gap > window
    lead, lag, same, _, _ = cl.match_events(buys, FOLLOWERS, window=3)
    assert not lead


def test_match_events_follower_events_collapsed_per_second() -> None:
    # two fills same second = one event
    buys = [(100, LEADER, "Up"), (102, FOL1, "Up"), (102, FOL1, "Up")]
    lead, _, _, f_ev, _ = cl.match_events(buys, FOLLOWERS, window=3)
    assert f_ev[FOL1] == 1
    assert lead[(LEADER, FOL1)] == 1


def test_group_market_files(tmp_path: Path) -> None:
    (tmp_path / "0xabc_0.json").write_text("[]")
    (tmp_path / "0xabc_1000.json").write_text("[]")
    (tmp_path / "0xdef_0.json").write_text("[]")
    groups = cl.group_market_files(tmp_path)
    assert len(groups["0xabc"]) == 2 and len(groups["0xdef"]) == 1
