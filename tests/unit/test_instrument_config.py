"""乐器配置的回归测试。

把 2026-09-25 的游戏内实测结论（见 `docs/design/DESIGN_SUMMARY_FOR_OPENSPEC.md` §2）
固化成断言：配置若被误改，测试必须失败，而不是悄悄改变演奏音高。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "instrument.json"

# 大调音阶：简谱音级 1..7 相对主音的半音数
DEGREE_SEMITONES: dict[int, int] = {1: 0, 2: 2, 3: 4, 4: 5, 5: 7, 6: 9, 7: 11}


@pytest.fixture(scope="module")
def config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def key_semitone(key: dict) -> int:
    """单个键在无修饰键时发出的音高（相对中音 1 的半音数）。"""
    return DEGREE_SEMITONES[key["degree"]] + 12 * key["octave"]


def set_offset(config: dict, buttons: list[str]) -> int:
    """修饰键组合的偏移 = 各键偏移之和（实测为可叠加）。"""
    by_button = {m["button"]: m["semitone"] for m in config["modifiers"]}
    return sum(by_button[button] for button in buttons)


def modifier_offsets(config: dict, *, include_assumed: bool = True) -> list[int]:
    """可用修饰组合的偏移列表；`include_assumed=False` 时只用已实测的组合。"""
    return [
        set_offset(config, entry["buttons"])
        for entry in config["modifier_sets"]
        if include_assumed or entry["status"] == "verified"
    ]


def reachable_semitones(config: dict, *, include_assumed: bool = True) -> set[int]:
    """所有可达音高 = 基础键 × 允许的修饰组合。"""
    offsets = modifier_offsets(config, include_assumed=include_assumed)
    return {key_semitone(k) + off for k in config["keys"] for off in offsets}


def test_keys_are_the_eight_measured_keys(config) -> None:
    assert [k["key"] for k in config["keys"]] == ["z", "x", "c", "v", "b", "n", "m", ","]
    assert [(k["degree"], k["octave"]) for k in config["keys"]] == [
        (1, 0),
        (2, 0),
        (3, 0),
        (4, 0),
        (5, 0),
        (6, 0),
        (7, 0),
        (1, 1),
    ]


def test_modifier_semitones_match_in_game_measurement(config) -> None:
    assert {m["button"]: m["semitone"] for m in config["modifiers"]} == {
        "left": -12,   # 降一个八度（游戏内显示：数字下方带点）
        "middle": 1,   # 升半音（游戏内显示：数字左上角带 #）
        "right": 12,   # 升一个八度（游戏内显示：数字上方带点）
    }
    assert config["verified"] is True


def test_modifier_sets_reference_known_buttons_and_sum_correctly(config) -> None:
    known = {m["button"] for m in config["modifiers"]}
    offsets = {}
    for entry in config["modifier_sets"]:
        assert set(entry["buttons"]) <= known, entry
        assert entry["status"] in {"verified", "assumed"}, entry
        offsets[tuple(entry["buttons"])] = set_offset(config, entry["buttons"])

    assert offsets == {
        (): 0,
        ("left",): -12,
        ("middle",): 1,
        ("right",): 12,
        ("left", "middle"): -11,   # 用户实测：左键基础上全部加 #
        ("middle", "right"): 13,   # 用户实测：右键 + 中键同样生效
    }


def test_no_assumed_combos_remain(config) -> None:
    """所有列出的组合都必须实测过；将来新增未实测组合时本测试会失败。"""
    assumed = [tuple(e["buttons"]) for e in config["modifier_sets"] if e["status"] == "assumed"]
    assert assumed == []


def test_base_keys_are_middle_octave_major_scale_plus_high_do(config) -> None:
    assert [key_semitone(k) for k in config["keys"]] == [0, 2, 4, 5, 7, 9, 11, 12]


def test_verified_setups_cover_low_to_high_do_chromatically(config) -> None:
    """只用已实测的组合，低音 1（-12）到高音 1̇（13）的 26 个半音必须全部可达。"""
    assert set(range(-12, 14)) <= reachable_semitones(config)


def test_verified_setups_cover_three_chromatic_octaves(config) -> None:
    """加上两个组合键后，低音 1（-12）到两点 1（24）共 37 个半音全部可达。"""
    reachable = reachable_semitones(config)
    assert set(range(-12, 25)) <= reachable
    assert len([s for s in reachable if -12 <= s <= 24]) == 37
