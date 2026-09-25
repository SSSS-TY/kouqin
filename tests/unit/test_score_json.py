"""J-01…J-03：`.kq.json` 往返无损（SPEC §3.5）。"""

from __future__ import annotations

from pathlib import Path

from kouqin.scores.json_score import dump_score_json, load_score_json
from kouqin.scores.kq import parse_kq

from tests.helpers import score_text


def note_tuples(score):
    return [(n.start_beat, n.duration_beat, n.pitch, n.tie) for n in score.notes]


def test_j01_json_round_trip_keeps_every_note(tmp_path: Path) -> None:
    original = parse_kq(score_text("advanced.kq"))
    path = tmp_path / "advanced.kq.json"
    dump_score_json(original, path)
    loaded = load_score_json(path)

    assert note_tuples(loaded) == note_tuples(original)
    assert (loaded.title, loaded.tempo_bpm, loaded.meter, loaded.transpose) == (
        original.title,
        original.tempo_bpm,
        original.meter,
        original.transpose,
    )


def test_j02_rest_survives_round_trip(tmp_path: Path) -> None:
    score = parse_kq("0- 1")
    path = tmp_path / "rest.kq.json"
    dump_score_json(score, path)
    loaded = load_score_json(path)
    assert loaded.notes[0].pitch is None
    assert loaded.notes[0].duration_beat == 2.0


def test_j03_fractional_durations_stay_exact(tmp_path: Path) -> None:
    score = parse_kq("5_ 5_. 5__")
    path = tmp_path / "fractions.kq.json"
    dump_score_json(score, path)
    loaded = load_score_json(path)
    assert [n.duration_beat for n in loaded.notes] == [0.5, 0.75, 0.25]

