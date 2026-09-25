"""C-01…C-14：演奏计划编译（SPEC §5）。

所有时间期望都是按 SPEC 规则手算出来的，注释里给出算式，便于复核。
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from kouqin.core.compile import PlanError, compile_plan
from kouqin.core.instrument import load_instrument
from kouqin.core.score import Note, Score
from kouqin.scores.kq import parse_kq
from kouqin.settings import load_settings

from tests.helpers import PINNED_PLAYBACK, score_text, shipped_instrument, write_instrument, write_settings


@pytest.fixture
def instrument(tmp_path: Path):
    return load_instrument(write_instrument(tmp_path, shipped_instrument()))


def compile_text(text: str, tmp_path: Path, instrument, **playback):
    score = parse_kq(text)
    settings = load_settings(write_settings(tmp_path, playback=playback or None))
    return compile_plan(score, instrument, settings)


def times(plan) -> list[float]:
    return [event.t_ms for event in plan.events]


def sequence(plan) -> list[tuple[str, str]]:
    return [(event.op, event.arg) for event in plan.events]


def test_c01_simple_fixture_note_times(tmp_path: Path, instrument) -> None:
    plan = compile_text(score_text("simple.kq"), tmp_path, instrument)
    assert [(n.start_ms, n.duration_ms, n.pitch) for n in plan.notes] == [
        (0, 600, 0),
        (600, 600, 0),
        (1200, 600, 7),
        (1800, 600, 7),
        (2400, 600, 9),
        (3000, 600, 9),
        (3600, 1200, 7),
        (4800, 600, 5),
        (5400, 600, 5),
        (6000, 600, 4),
        (6600, 600, 4),
        (7200, 600, 2),
        (7800, 600, 2),
        (8400, 1200, 0),
    ]


def test_c02_speed_halves_all_times(tmp_path: Path, instrument) -> None:
    normal = compile_text(score_text("simple.kq"), tmp_path, instrument)
    fast = compile_plan(
        parse_kq(score_text("simple.kq")),
        instrument,
        load_settings(write_settings(tmp_path, playback={"countdown_ms": 0})),
        speed=2.0,
    )
    assert [n.start_ms for n in fast.notes] == [n.start_ms / 2 for n in normal.notes]
    assert [n.duration_ms for n in fast.notes] == [n.duration_ms / 2 for n in normal.notes]


def test_c03_transpose_shifts_pitch_and_reassigns_fingering(tmp_path: Path, instrument) -> None:
    plan = compile_text("@transpose 2\n\n1 1 1 1", tmp_path, instrument)
    assert [n.pitch for n in plan.notes] == [2, 2, 2, 2]
    assert {n.fingering.key for n in plan.notes} == {"x"}
    assert {n.fingering.buttons for n in plan.notes} == {()}


def test_c04_long_note_is_split_within_its_own_duration(tmp_path: Path, instrument) -> None:
    # 5 拍 @ tempo 100 = 3000 ms；hold = max(1, min(3000, max(2970, 40))) = 2970
    # n = ceil((2970 + 30) / (2000 + 30)) = 2；每段 = (2970 − 30) / 2 = 1470
    plan = compile_text("@tempo 100\n\n1----", tmp_path, instrument, sustain_limit_ms=2000)
    assert sequence(plan) == [("key_down", "z"), ("key_up", "z"), ("key_down", "z"), ("key_up", "z")]
    assert times(plan) == [0, 1470, 1500, 2970]
    for down, up in zip(times(plan)[::2], times(plan)[1::2]):
        assert up - down <= 2000


def test_c05_sustain_unknown_keeps_single_hold(tmp_path: Path, instrument) -> None:
    plan = compile_text("@tempo 100\n\n1----", tmp_path, instrument)
    assert times(plan) == [0, 2970]


def test_c06_retrigger_disabled_keeps_single_hold(tmp_path: Path, instrument) -> None:
    plan = compile_text(
        "@tempo 100\n\n1----", tmp_path, instrument, sustain_limit_ms=2000, retrigger_long_notes=False
    )
    assert times(plan) == [0, 2970]


def test_c07_adding_modifier_happens_after_key_release(tmp_path: Path, instrument) -> None:
    # tempo 120 → 500 ms/拍；两音都是 1 拍，hold = max(1, min(500, max(470, 40))) = 470
    plan = compile_text("@tempo 120\n\n1 1,", tmp_path, instrument)
    assert sequence(plan) == [
        ("key_down", "z"),
        ("key_up", "z"),
        ("mouse_down", "left"),
        ("key_down", "z"),
        ("key_up", "z"),
        ("mouse_up", "left"),
    ]
    assert times(plan) == [0, 470, 490, 500, 970, 980]


def test_c08_removing_modifier_and_negative_lead_shifts_plan(tmp_path: Path, instrument) -> None:
    plan = compile_text("@tempo 120\n\n1, 1", tmp_path, instrument)
    assert sequence(plan) == [
        ("mouse_down", "left"),
        ("key_down", "z"),
        ("key_up", "z"),
        ("mouse_up", "left"),
        ("key_down", "z"),
        ("key_up", "z"),
    ]
    assert all(t >= 0 for t in times(plan))
    # 平移前：−10, 0, 470, 480, 500, 970 → 整体后移 10 ms
    assert plan.offset_ms == 10
    assert times(plan) == [0, 10, 480, 490, 510, 980]


def test_c09_insufficient_switch_time_shifts_note_and_warns(tmp_path: Path, instrument) -> None:
    # tempo 600 → 100 ms/拍；`1__` 与 `1,__` 各 0.25 拍 = 25 ms，间隔 0 ms
    plan = compile_text("@tempo 600\n\n1__ 1,__", tmp_path, instrument)
    assert any(issue.code == "CP002" and issue.level == "warning" for issue in plan.issues)

    first_up = plan.events[1].t_ms
    second_down = plan.events[3].t_ms
    assert second_down >= first_up + 20  # 需要的换修饰时间 = tail 10 + 1×lead 10


def test_c10_tie_merges_into_single_hold(tmp_path: Path, instrument) -> None:
    # 两个 1 拍的 1（tempo 100 → 各 600 ms），连音后 hold = max(1, min(1200, max(1170, 40))) = 1170
    plan = compile_text("@tempo 100\n\n1 ~1", tmp_path, instrument)
    assert sequence(plan) == [("key_down", "z"), ("key_up", "z")]
    assert times(plan) == [0, 1170]


def test_c11_unreachable_note_reports_line(tmp_path: Path, instrument) -> None:
    with pytest.raises(PlanError) as excinfo:
        compile_text("@transpose 30\n\n1", tmp_path, instrument)
    issue = next(i for i in excinfo.value.issues if i.code == "CP001")
    assert issue.line == 3


def test_c12_fingering_matches_events(tmp_path: Path, instrument) -> None:
    plan = compile_text(score_text("advanced.kq"), tmp_path, instrument)
    event_args = {event.arg for event in plan.events}
    for note in plan.notes:
        assert note.fingering.key in event_args
        for button in note.fingering.buttons:
            assert button in event_args
    mouse_args = {event.arg for event in plan.events if event.op.startswith("mouse")}
    assert mouse_args <= {"left", "middle", "right"}


def test_c13_params_come_from_settings(tmp_path: Path, instrument) -> None:
    plan = compile_text("1", tmp_path, instrument)
    assert plan.params == PINNED_PLAYBACK


def test_c14_compiling_two_thousand_notes_is_fast(tmp_path: Path, instrument) -> None:
    notes = tuple(
        Note(start_beat=float(i), duration_beat=1.0, pitch=0, repr="1", tie=False, line=1)
        for i in range(2000)
    )
    score = Score(
        title="perf", tempo_bpm=120, meter="4/4", transpose=0, notes=notes, source=None, issues=()
    )
    settings = load_settings(write_settings(tmp_path, playback={"countdown_ms": 0}))

    started = time.perf_counter()
    plan = compile_plan(score, instrument, settings)
    elapsed = time.perf_counter() - started

    assert len(plan.notes) == 2000
    assert elapsed < 1.0, f"编译 2000 音耗时 {elapsed:.3f}s，疑似 O(n²) 退化"


def test_c15_same_modifier_set_is_not_repressed(tmp_path: Path, instrument) -> None:
    """SPEC §5.4-3：相邻两音组合相同 → 不发任何鼠标事件（整段只按放一次）。"""
    plan = compile_text("@tempo 120\n\n1, 1,", tmp_path, instrument)
    assert sequence(plan) == [
        ("mouse_down", "left"),
        ("key_down", "z"),
        ("key_up", "z"),
        ("key_down", "z"),
        ("key_up", "z"),
        ("mouse_up", "left"),
    ]
    # 平移前：−10, 0, 470, 500, 970, 980
    assert times(plan) == [0, 10, 480, 510, 980, 990]
