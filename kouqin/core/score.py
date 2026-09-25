"""曲谱数据模型与错误类型（SPEC §3.3、§9）。

`Note.pitch` 是**相对乐器基准音（z 键 = 中音 1）的半音偏移**，不含整体移调；
移调在编译阶段叠加（SPEC §5.2）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

ERROR = "error"
WARNING = "warning"
INFO = "info"


@dataclass(frozen=True)
class Issue:
    """一条诊断信息（错误 / 警告 / 提示），对应 SPEC §9 的错误码表。"""

    code: str
    level: str
    message: str
    line: int | None = None
    beat: float | None = None


class ScoreError(Exception):
    """曲谱层面的致命错误；`issues` 至少包含一条 `level == "error"` 的记录。"""

    def __init__(self, issues: list[Issue] | tuple[Issue, ...]) -> None:
        self.issues: tuple[Issue, ...] = tuple(issues)
        summary = "；".join(f"{i.code}: {i.message}" for i in self.issues) or "未知错误"
        super().__init__(summary)


@dataclass(frozen=True)
class Note:
    """一个音（或休止）。`start_beat` 为相对曲谱开头的拍数。"""

    start_beat: float
    duration_beat: float
    pitch: int | None
    repr: str
    tie: bool = False
    line: int = 1


@dataclass(frozen=True)
class Score:
    """一首曲子。`notes` 按 `start_beat` 升序且不重叠（单音线）。"""

    title: str
    tempo_bpm: float
    meter: str
    transpose: int
    notes: tuple[Note, ...]
    source: str | None = None
    issues: tuple[Issue, ...] = field(default=())

    @property
    def duration_beat(self) -> float:
        return sum(note.duration_beat for note in self.notes)

    @property
    def note_count(self) -> int:
        return sum(1 for note in self.notes if note.pitch is not None)

