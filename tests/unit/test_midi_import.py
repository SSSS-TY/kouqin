"""M-00…M-09：MIDI（SMF 0/1）导入（SPEC §3.6、§9 的 MD 错误码）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from kouqin.core.score import ScoreError
from kouqin.scores.midi import import_midi

from tests.helpers import MIDI_DIR, PINNED_MIDI
from tools.make_test_midi import build_all


def import_fixture(name: str, **reference):
    ref = {**PINNED_MIDI, **reference}
    return import_midi(MIDI_DIR / name, ref["reference_note"], ref["reference_semitone"])


def note_tuples(score):
    return [(n.start_beat, n.duration_beat, n.pitch) for n in score.notes]


def test_m00_fixtures_match_generator() -> None:
    for name, payload in build_all().items():
        assert (MIDI_DIR / name).read_bytes() == payload, name


def test_m01_multi_track_merges_into_single_voice_line() -> None:
    result = import_fixture("sample_multi.mid")
    assert note_tuples(result.score) == [
        (0.0, 1.0, 0),
        (1.0, 1.0, 4),
        (2.0, 1.0, 11),
        (3.0, 1.0, 12),
        (4.0, 1.0, -12),
        (5.0, 1.0, -10),
    ]
    starts = [n.start_beat for n in result.score.notes]
    assert starts == sorted(starts)


def test_m02_format0_with_running_status() -> None:
    result = import_fixture("sample_format0.mid")
    assert note_tuples(result.score) == [(0.0, 1.0, 0), (1.0, 1.0, 2)]


def test_m03_drum_channel_is_ignored() -> None:
    result = import_fixture("sample_multi.mid")
    # 打击轨在 tick 0/480/960/1440 各有一个音；若被计入，音符数会明显增多
    assert len(result.score.notes) == 6
    assert result.dropped_notes == 1  # 只应丢和弦里的那一个


def test_m04_chord_keeps_highest_note_and_reports_drop() -> None:
    result = import_fixture("sample_multi.mid")
    assert result.dropped_notes == 1
    assert any(issue.code == "MD006" for issue in result.issues)
    # 和弦处保留 71（s=11），而不是 67（s=7）
    assert 11 in [n.pitch for n in result.score.notes]
    assert 7 not in [n.pitch for n in result.score.notes]


def test_m05_tempo_meta_or_default() -> None:
    assert import_fixture("sample_multi.mid").score.tempo_bpm == 150  # 400000 µs/拍
    assert import_fixture("sample_format0.mid").score.tempo_bpm == 120  # 无 tempo 元事件


def test_m06_tick_to_beat_uses_division() -> None:
    result = import_fixture("sample_multi.mid")  # division = 480
    assert [n.start_beat for n in result.score.notes] == [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]


def test_m07_reference_note_shifts_everything() -> None:
    base = import_fixture("sample_format0.mid")
    shifted = import_fixture("sample_format0.mid", reference_note=62)
    assert [n.pitch for n in shifted.score.notes] == [p - 2 for p in (n.pitch for n in base.score.notes)]


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("bad_format2.mid", "MD002"),
        ("bad_smpte.mid", "MD003"),
        ("no_notes.mid", "MD004"),
        ("not_midi.bin", "MD001"),
    ],
)
def test_m08_bad_files_report_specific_errors(name: str, code: str) -> None:
    with pytest.raises(ScoreError) as excinfo:
        import_fixture(name)
    assert excinfo.value.issues[0].code == code


def test_m09_out_of_range_reports_md005_with_transpose_hint() -> None:
    with pytest.raises(ScoreError) as excinfo:
        import_fixture("out_of_range.mid")
    issue = excinfo.value.issues[0]
    assert issue.code == "MD005"
    assert "移调" in issue.message
