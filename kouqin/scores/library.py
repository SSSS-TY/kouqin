"""曲谱库：扫描目录、读取元信息、保存与删除（SPEC §4）。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kouqin.core.instrument import Instrument, reachable
from kouqin.core.score import Score, ScoreError
from kouqin.scores.json_score import dump_score_json, load_score_json
from kouqin.scores.kq import parse_kq_file, render_kq
from kouqin.scores.midi import import_midi

SUPPORTED_SUFFIXES = (".kq", ".json", ".mid", ".midi")


@dataclass(frozen=True)
class ScoreEntry:
    path: Path
    title: str
    note_count: int
    duration_beat: float
    tempo_bpm: float
    unreachable: int
    error: str | None = None

    @property
    def status_text(self) -> str:
        if self.error:
            return f"解析失败：{self.error}"
        return "可完整演奏" if self.unreachable == 0 else f"{self.unreachable} 个音不可达"


def load_score(path: str | Path, instrument: Instrument, midi_reference: tuple[int, int] = (60, 0)) -> Score:
    """按扩展名读取曲谱。"""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in {".mid", ".midi"}:
        return import_midi(path, *midi_reference).score
    if suffix == ".json":
        return load_score_json(path)
    return parse_kq_file(path)


def count_unreachable(score: Score, instrument: Instrument) -> int:
    """统计超出乐器音域的音（不含休止），用于曲谱库的「可完整演奏」标记。"""
    available = reachable(instrument)
    return sum(1 for note in score.notes if note.pitch is not None and note.pitch + score.transpose not in available)


def list_scores(
    directory: str | Path,
    instrument: Instrument,
    midi_reference: tuple[int, int] = (60, 0),
) -> list[ScoreEntry]:
    """扫描目录下的曲谱文件，解析失败的文件也会列出（带错误说明）。"""
    directory = Path(directory)
    if not directory.is_dir():
        return []

    entries: list[ScoreEntry] = []
    for path in sorted(directory.iterdir()):
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        try:
            score = load_score(path, instrument, midi_reference)
        except (ScoreError, ValueError, OSError, KeyError) as exc:
            entries.append(
                ScoreEntry(path=path, title=path.stem, note_count=0, duration_beat=0.0, tempo_bpm=0.0,
                           unreachable=0, error=str(exc))
            )
            continue
        entries.append(
            ScoreEntry(
                path=path,
                title=score.title,
                note_count=score.note_count,
                duration_beat=score.duration_beat,
                tempo_bpm=score.tempo_bpm,
                unreachable=count_unreachable(score, instrument),
            )
        )
    return entries


def save_score(score: Score, path: str | Path) -> None:
    """把曲谱写出为 `.kq`（默认）或 `.kq.json`。"""
    path = Path(path)
    if path.suffix.lower() == ".json":
        dump_score_json(score, path)
    else:
        path.write_text(render_kq(score), encoding="utf-8")


def delete_score(path: str | Path) -> None:
    """删除曲谱文件（调用方负责确认）。"""
    Path(path).unlink(missing_ok=True)

