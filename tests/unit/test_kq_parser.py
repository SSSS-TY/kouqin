"""K-01…K-22：文本简谱 `.kq` 解析（SPEC §3.4）。

错误用例统一用「恰好一处错误」的样例，断言错误码与行号。
"""

from __future__ import annotations

import pytest

from kouqin.core.score import ScoreError
from kouqin.scores.kq import parse_kq, render_kq

from tests.helpers import score_text


def first_error(text: str):
    with pytest.raises(ScoreError) as excinfo:
        parse_kq(text)
    return excinfo.value.issues[0]


def test_k01_single_note_defaults_to_one_beat() -> None:
    note = parse_kq("1").notes[0]
    assert (note.start_beat, note.duration_beat, note.pitch) == (0.0, 1.0, 0)


@pytest.mark.parametrize(("token", "beats"), [("5-", 2.0), ("5--", 3.0)])
def test_k02_dash_extends_by_one_beat(token: str, beats: float) -> None:
    assert parse_kq(token).notes[0].duration_beat == beats


@pytest.mark.parametrize(("token", "beats"), [("5.", 1.5), ("5-.", 3.0)])
def test_k03_dot_multiplies_by_one_point_five(token: str, beats: float) -> None:
    assert parse_kq(token).notes[0].duration_beat == beats


@pytest.mark.parametrize(("token", "beats"), [("5_", 0.5), ("5__", 0.25), ("5_.", 0.75)])
def test_k04_underscore_halves_last(token: str, beats: float) -> None:
    assert parse_kq(token).notes[0].duration_beat == beats


@pytest.mark.parametrize(("token", "pitch"), [("#1", 1), ("b3", 3)])
def test_k05_accidentals(token: str, pitch: int) -> None:
    assert parse_kq(token).notes[0].pitch == pitch


@pytest.mark.parametrize(("token", "pitch"), [("1'", 12), ("1''", 24), ("1,", -12), ("1,,", -24)])
def test_k06_octave_marks(token: str, pitch: int) -> None:
    assert parse_kq(token).notes[0].pitch == pitch


def test_k07_rest_has_no_pitch_but_keeps_duration() -> None:
    notes = parse_kq("0- 1").notes
    assert notes[0].pitch is None
    assert notes[0].duration_beat == 2.0
    assert notes[1].start_beat == 2.0


def test_k08_barlines_and_whitespace_do_not_affect_time() -> None:
    notes = parse_kq("1 | 2").notes
    assert [(n.start_beat, n.pitch) for n in notes] == [(0.0, 0), (1.0, 2)]


def test_k09_comments_are_ignored_and_line_numbers_are_kept() -> None:
    text = "@title x\n\n# 这是注释\n1 2\n"
    notes = parse_kq(text).notes
    assert [n.pitch for n in notes] == [0, 2]
    assert notes[0].line == 4


def test_k10_simple_fixture_totals() -> None:
    score = parse_kq(score_text("simple.kq"))
    assert score.title == "小星星"
    assert score.tempo_bpm == 100
    assert score.meter == "4/4"
    assert len(score.notes) == 14
    assert sum(n.duration_beat for n in score.notes) == 16.0


def test_k11_defaults_when_meta_missing() -> None:
    score = parse_kq("1")
    assert score.title == "未命名"
    assert score.tempo_bpm == 120
    assert score.transpose == 0


def test_k12_advanced_fixture_every_note() -> None:
    score = parse_kq(score_text("advanced.kq"))
    assert score.transpose == 2
    expected = [
        (0.0, 1.0, 6, False),
        (1.0, 1.0, 3, False),
        (2.0, 1.5, 7, False),
        (3.5, 0.5, None, False),
        (4.0, 0.5, 9, False),
        (4.5, 0.5, 11, False),
        (5.0, 1.0, 12, False),
        (6.0, 1.0, 12, True),
        (7.0, 1.0, -10, False),
    ]
    assert [(n.start_beat, n.duration_beat, n.pitch, n.tie) for n in score.notes] == expected


def test_k13_tie_flag_on_same_pitch() -> None:
    notes = parse_kq("1 1~").notes
    assert notes[0].tie is False
    assert notes[1].tie is True


def test_k14_tie_with_different_pitch_is_rejected() -> None:
    error = first_error(score_text("bad_tie.kq"))
    assert (error.code, error.line) == ("KQ008", 5)


def test_k14b_tie_on_first_note_is_rejected() -> None:
    assert first_error("~1").code == "KQ008"


def test_k15_unknown_meta_name() -> None:
    error = first_error(score_text("bad_meta_name.kq"))
    assert (error.code, error.line) == ("KQ002", 2)


def test_k16_invalid_meta_values() -> None:
    assert first_error(score_text("bad_meta_value.kq")).code == "KQ003"
    assert first_error("@transpose 1.5\n1").code == "KQ003"
    assert first_error("@meter 4/0\n1").code == "KQ003"


def test_k17_unparsable_note_token() -> None:
    error = first_error(score_text("bad_note.kq"))
    assert (error.code, error.line) == ("KQ004", 3)
    assert "9" in error.message


def test_k18_rest_with_marks_is_rejected() -> None:
    assert first_error(score_text("bad_rest_mark.kq")).code == "KQ005"
    assert first_error("0'").code == "KQ005"


def test_k19_empty_score() -> None:
    assert first_error(score_text("empty.kq")).code == "KQ010"


def test_k20_pitch_out_of_representable_range() -> None:
    assert first_error(score_text("bad_range.kq")).code == "KQ011"


def test_k21_bar_length_mismatch_is_only_a_warning() -> None:
    score = parse_kq(score_text("bad_meter.kq"))
    assert [n.pitch for n in score.notes] == [0, 2, 4]
    assert any(issue.code == "KQ009" and issue.level == "warning" for issue in score.issues)


@pytest.mark.parametrize("name", ["simple.kq", "advanced.kq"])
def test_k22_render_then_parse_round_trip(name: str) -> None:
    original = parse_kq(score_text(name))
    reparsed = parse_kq(render_kq(original))
    assert [(n.start_beat, n.duration_beat, n.pitch, n.tie) for n in reparsed.notes] == [
        (n.start_beat, n.duration_beat, n.pitch, n.tie) for n in original.notes
    ]
    assert (reparsed.title, reparsed.tempo_bpm, reparsed.transpose) == (
        original.title,
        original.tempo_bpm,
        original.transpose,
    )
