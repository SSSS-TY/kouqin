"""播放参数配置的回归测试。

把两件事固定下来：① 用户明确要求（不使用 F8/F9）；② 「未测项不得伪装成已测」——
`sustain_limit_ms` 在 P0-7 完成前必须保持 null，且每个参数都要有依据说明。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "settings.json"


@pytest.fixture(scope="module")
def config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def test_hotkeys_avoid_f8_and_f9(config) -> None:
    hotkeys = config["hotkeys"]
    assert set(hotkeys) == {"toggle_play", "pause_resume", "panic_release"}
    assert not any("F8" in value or "F9" in value for value in hotkeys.values())


def test_hotkeys_are_combos_not_bare_instrument_keys(config) -> None:
    """热键必须是带修饰键的组合，且不使用口琴键位本身。"""
    instrument_keys = set("zxcvbnm,")
    for action, value in config["hotkeys"].items():
        parts = [part.strip().lower() for part in value.split("+")]
        assert len(parts) >= 2, (action, value)
        assert all(part not in instrument_keys for part in parts), (action, value)


def test_playback_values_are_within_measured_bounds(config) -> None:
    playback = config["playback"]
    assert playback["min_hold_ms"] >= 20          # P0-3：20 ms 即可听见
    assert playback["note_gap_ms"] >= 0
    assert playback["modifier_lead_ms"] >= 0
    assert playback["modifier_tail_ms"] >= 0
    assert playback["countdown_ms"] >= 0
    assert isinstance(playback["retrigger_long_notes"], bool)


def test_sustain_limit_stays_unmeasured_until_tested(config) -> None:
    """P0-7 完成前，长音衰减上限必须保持 null（不得猜一个数值填进去）。"""
    assert config["playback"]["sustain_limit_ms"] is None


def test_every_setting_is_explained(config) -> None:
    """防止有人改了参数却不更新依据说明。"""
    assert set(config["playback"]) - set(config["notes"]) == set()
