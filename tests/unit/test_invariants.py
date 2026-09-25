"""R-01…R-04：随机曲谱上的计划不变量（SPEC §5.5）与随机往返。

固定随机种子，失败可复现；随机目标音高先落在可达区间 [−12, 24] 内，再反推 `Note.pitch`
（`pitch = target − transpose`），保证失败只可能来自不变量而非「不可达」。
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from kouqin.core.compile import compile_plan
from kouqin.core.instrument import load_instrument
from kouqin.core.score import Note, Score
from kouqin.scores.kq import parse_kq, render_kq
from kouqin.settings import load_settings

from tests.helpers import shipped_instrument, write_instrument, write_settings

DURATIONS = [0.125, 0.25, 0.5, 1.0, 2.0, 4.0]


def random_score(rng: random.Random, note_count: int = 40) -> Score:
    transpose = rng.randint(-3, 3)
    notes = []
    beat = 0.0
    for _ in range(note_count):
        duration = rng.choice(DURATIONS)
        target = rng.randint(-12, 24)
        notes.append(
            Note(
                start_beat=beat,
                duration_beat=duration,
                pitch=target - transpose,
                repr="1",
                tie=False,
                line=1,
            )
        )
        beat += duration
    return Score(
        title="random",
        tempo_bpm=rng.choice([60, 90, 120, 200, 600]),
        meter="4/4",
        transpose=transpose,
        notes=tuple(notes),
        source=None,
        issues=(),
    )


def assert_plan_invariants(plan) -> None:
    times = [event.t_ms for event in plan.events]
    assert times == sorted(times), "事件时间必须非递减"
    assert all(t >= 0 for t in times), "事件时间必须非负"

    pressed: set[str] = set()
    for event in plan.events:
        if event.op.endswith("_down"):
            assert event.arg not in pressed, f"{event.arg} 在未松开时被再次按下"
            pressed.add(event.arg)
        else:
            pressed.discard(event.arg)
    assert not pressed, f"计划结束时仍有按住的键：{sorted(pressed)}"

    for note in plan.notes:
        assert note.fingering.key, "每个非休止音都必须有指法"


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_r01_random_scores_keep_invariants(seed: int, tmp_path: Path) -> None:
    rng = random.Random(seed)
    instrument = load_instrument(write_instrument(tmp_path, shipped_instrument()))
    settings = load_settings(write_settings(tmp_path))
    for _ in range(40):
        assert_plan_invariants(compile_plan(random_score(rng), instrument, settings))


@pytest.mark.parametrize("seed", [11, 12, 13])
def test_r02_random_sustain_split_stays_within_limit(seed: int, tmp_path: Path) -> None:
    rng = random.Random(seed)
    instrument = load_instrument(write_instrument(tmp_path, shipped_instrument()))
    limit = rng.choice([500, 800, 1200, 2000, 3000])
    settings = load_settings(
        write_settings(tmp_path, playback={"sustain_limit_ms": limit, "retrigger_long_notes": True})
    )

    for _ in range(20):
        plan = compile_plan(random_score(rng), instrument, settings)
        assert_plan_invariants(plan)
        down_times = [e.t_ms for e in plan.events if e.op == "key_down"]
        up_times = [e.t_ms for e in plan.events if e.op == "key_up"]
        for down, up in zip(down_times, up_times):
            assert up - down <= limit


@pytest.mark.parametrize("speed", [0.5, 1.0, 1.5, 2.0])
def test_r03_random_speed_keeps_monotonic_times(speed: float, tmp_path: Path) -> None:
    rng = random.Random(99)
    instrument = load_instrument(write_instrument(tmp_path, shipped_instrument()))
    settings = load_settings(write_settings(tmp_path))
    for _ in range(20):
        assert_plan_invariants(compile_plan(random_score(rng), instrument, settings, speed=speed))


def test_r04_random_scores_survive_text_round_trip(tmp_path: Path) -> None:
    rng = random.Random(2026)
    for _ in range(20):
        score = random_score(rng, note_count=12)
        reparsed = parse_kq(render_kq(score))
        assert [(n.pitch, n.duration_beat) for n in reparsed.notes] == [
            (n.pitch, n.duration_beat) for n in score.notes
        ]
