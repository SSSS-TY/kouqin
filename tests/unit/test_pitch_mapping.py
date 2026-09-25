"""P-01…P-11：音高换算与指法选择（SPEC §3.2、§5.3）。

其中 P-05/P-07/P-08/P-09 用「测试里独立实现一遍优先级规则再与实现比对」的方式覆盖，
比单点断言更强。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kouqin.core.compile import PlanError, compile_plan
from kouqin.core.instrument import find_fingering, load_instrument, reachable
from kouqin.core.pitch import degree_semitone, key_semitone, modifier_offset
from kouqin.scores.kq import parse_kq
from kouqin.settings import load_settings

from tests.helpers import score_text, shipped_instrument, write_instrument, write_settings


@pytest.fixture
def instrument(tmp_path: Path):
    return load_instrument(write_instrument(tmp_path, shipped_instrument()))


def verified_offsets(instrument) -> list[int]:
    return [
        modifier_offset(entry.buttons, instrument.modifiers)
        for entry in instrument.modifier_sets
        if entry.status == "verified"
    ]


def test_p01_degree_semitone_major_scale() -> None:
    assert [degree_semitone(d) for d in range(1, 8)] == [0, 2, 4, 5, 7, 9, 11]


def test_p02_key_semitone_of_eight_keys(instrument) -> None:
    assert [key_semitone(k) for k in instrument.keys] == [0, 2, 4, 5, 7, 9, 11, 12]


def test_p03_modifier_set_offsets(instrument) -> None:
    by_buttons = {entry.buttons: modifier_offset(entry.buttons, instrument.modifiers) for entry in instrument.modifier_sets}
    assert by_buttons[()] == 0
    assert by_buttons[("left",)] == -12
    assert by_buttons[("middle",)] == 1
    assert by_buttons[("right",)] == 12
    assert by_buttons[("left", "middle")] == -11
    assert by_buttons[("middle", "right")] == 13


def test_p04_reachable_covers_three_chromatic_octaves(instrument) -> None:
    notes = reachable(instrument)
    assert set(range(-12, 25)) <= notes


def candidates_for(instrument, target: int, buttons: tuple[str, ...], ignore_status: bool = False):
    """按 SPEC §5.3 独立实现候选筛选，用来与 find_fingering 的结果比对。"""
    offsets = [
        (entry.buttons, modifier_offset(entry.buttons, instrument.modifiers))
        for entry in instrument.modifier_sets
        if ignore_status or entry.status == "verified"
    ]
    order = {k.key: index for index, k in enumerate(instrument.keys)}
    result = []
    for key in instrument.keys:
        for set_buttons, offset in offsets:
            if key_semitone(key) + offset == target:
                result.append((key.key, set_buttons))
    return result, order


def expected_fingering(instrument, target: int, prefer: tuple[str, ...] = ()):
    cands, order = candidates_for(instrument, target, prefer)
    if not cands:
        return None
    fewest = min(len(buttons) for _, buttons in cands)
    cands = [c for c in cands if len(c[1]) == fewest]
    if any(buttons == prefer for _, buttons in cands):
        cands = [c for c in cands if c[1] == prefer]
    key, buttons = min(cands, key=lambda c: order[c[0]])
    return key, buttons


def test_p05_every_reachable_note_has_matching_fingering(instrument) -> None:
    for target in range(-12, 25):
        fingering = find_fingering(instrument, target)
        assert fingering is not None, target
        key = next(k for k in instrument.keys if k.key == fingering.key)
        assert key_semitone(key) + modifier_offset(fingering.buttons, instrument.modifiers) == target


def test_p06_unreachable_notes_return_none(instrument) -> None:
    assert find_fingering(instrument, 30) is None
    assert find_fingering(instrument, -17) is None
    assert find_fingering(instrument, 26) is None


def test_p07_prefers_no_modifier_for_base_note(instrument) -> None:
    fingering = find_fingering(instrument, 0)
    assert (fingering.key, fingering.buttons) == ("z", ())


def test_p08_matches_spec_priority_for_all_targets(instrument) -> None:
    """P-07/P-08/P-09 合并：对每个目标音，实现的选法必须等于按 SPEC 规则算出的结果。"""
    prefers = [(), ("left",), ("middle",), ("right",), ("left", "middle")]
    for target in range(-12, 25):
        for prefer in prefers:
            fingering = find_fingering(instrument, target, prefer_buttons=prefer)
            assert fingering is not None
            assert (fingering.key, fingering.buttons) == expected_fingering(instrument, target, prefer), (target, prefer)


def test_p09_single_button_beats_two_button_combo(instrument) -> None:
    # s = 17 可由 (v, right) 一键达成，也可由 (c, middle+right) 两键达成 → 取一键
    assert (find_fingering(instrument, 17).key, find_fingering(instrument, 17).buttons) == ("v", ("right",))


def test_p10_assumed_combo_is_not_used(tmp_path: Path, instrument) -> None:
    data = shipped_instrument()
    for entry in data["modifier_sets"]:
        if entry["buttons"] == ["middle", "right"]:
            entry["status"] = "assumed"
    restricted = load_instrument(write_instrument(tmp_path, data, "assumed.json"))

    # s = 25 只能由「, + middle+right」达成
    assert 25 in reachable(instrument)
    assert 25 not in reachable(restricted)
    assert find_fingering(restricted, 25) is None


def test_p11_unverified_instrument_blocks_compile(tmp_path: Path) -> None:
    data = shipped_instrument()
    data["verified"] = False
    instrument = load_instrument(write_instrument(tmp_path, data, "unverified.json"))
    score = parse_kq(score_text("golden_bar.kq"))
    settings = load_settings(write_settings(tmp_path))

    with pytest.raises(PlanError) as excinfo:
        compile_plan(score, instrument, settings)

    assert any(issue.code == "CP004" for issue in excinfo.value.issues)
