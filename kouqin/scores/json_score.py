"""`.kq.json` 的读写（SPEC §3.5，往返无损）。"""

from __future__ import annotations

import json
from pathlib import Path

from kouqin.core.score import Note, Score


def dump_score_json(score: Score, path: str | Path) -> None:
    """写出 JSON 曲谱（UTF-8、缩进 2、中文不转义）。"""
    data = {
        "version": 1,
        "title": score.title,
        "tempo_bpm": score.tempo_bpm,
        "meter": score.meter,
        "transpose": score.transpose,
        "notes": [
            {
                "start_beat": note.start_beat,
                "duration_beat": note.duration_beat,
                "pitch": note.pitch,
                "repr": note.repr,
                "tie": note.tie,
                "line": note.line,
            }
            for note in score.notes
        ],
    }
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_score_json(path: str | Path) -> Score:
    """读取 JSON 曲谱。"""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    return Score(
        title=data.get("title", "未命名"),
        tempo_bpm=float(data.get("tempo_bpm", 120)),
        meter=data.get("meter", "4/4"),
        transpose=int(data.get("transpose", 0)),
        notes=tuple(
            Note(
                start_beat=float(item["start_beat"]),
                duration_beat=float(item["duration_beat"]),
                pitch=None if item["pitch"] is None else int(item["pitch"]),
                repr=item.get("repr", ""),
                tie=bool(item.get("tie", False)),
                line=int(item.get("line", 1)),
            )
            for item in data.get("notes", [])
        ),
        source=str(path),
    )

