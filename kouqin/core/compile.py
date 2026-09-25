"""演奏计划编译（SPEC §5，含勘误 E1–E7）。

把「拍为单位」的曲谱换算成「绝对毫秒」的事件序列，并处理：
连音合并、长音切分、修饰键切换、整体移调、负时间平移与不变量校验。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from kouqin.core.instrument import Fingering, Instrument, find_fingering
from kouqin.core.score import Issue, Score, ScoreError


class PlanError(ScoreError):
    """编译失败；`issues` 里至少有一条 error。"""


@dataclass(frozen=True)
class PlanEvent:
    t_ms: int
    op: str          # key_down / key_up / mouse_down / mouse_up
    arg: str         # 键字符或 left/middle/right


@dataclass(frozen=True)
class PlanNote:
    index: int
    start_ms: int
    duration_ms: int
    pitch: int
    repr: str
    fingering: Fingering


@dataclass(frozen=True)
class Plan:
    version: int
    title: str
    tempo_bpm: float
    speed: float
    transpose: int
    source: str | None
    generated_at: str
    offset_ms: int
    params: dict[str, Any]
    issues: tuple[Issue, ...]
    notes: tuple[PlanNote, ...]
    events: tuple[PlanEvent, ...]

    @property
    def duration_ms(self) -> int:
        return self.events[-1].t_ms if self.events else 0

    def to_dict(self) -> dict[str, Any]:
        """产出 SPEC §3.7 的 JSON 结构。"""
        return {
            "version": self.version,
            "title": self.title,
            "tempo_bpm": self.tempo_bpm,
            "speed": self.speed,
            "transpose": self.transpose,
            "source": self.source,
            "generated_at": self.generated_at,
            "offset_ms": self.offset_ms,
            "params": dict(self.params),
            "issues": [
                {
                    "code": issue.code,
                    "level": issue.level,
                    "message": issue.message,
                    "line": issue.line,
                    "beat": issue.beat,
                }
                for issue in self.issues
            ],
            "notes": [
                {
                    "index": note.index,
                    "start_ms": note.start_ms,
                    "duration_ms": note.duration_ms,
                    "pitch": note.pitch,
                    "repr": note.repr,
                    "fingering": {"key": note.fingering.key, "buttons": list(note.fingering.buttons)},
                }
                for note in self.notes
            ],
            "events": [{"t_ms": event.t_ms, "op": event.op, "arg": event.arg} for event in self.events],
        }


@dataclass
class _PlayableNote:
    """编译中间态：一个可演奏音（连音已合并）。"""

    pitch: int
    repr: str
    start_ms: int
    duration_ms: int
    fingering: Fingering
    line: int
    hold_ms: int = 0


def _hold_ms(duration_ms: int, gap: int, min_hold: int) -> int:
    """SPEC §5.2（勘误 E1）：最短按时长不得突破音符自身时值。"""
    return max(1, min(duration_ms, max(duration_ms - gap, min_hold)))


def _split_segments(start_ms: int, hold_ms: int, sustain: int | None, retrigger: bool, gap: int) -> list[tuple[int, int]]:
    """长音切分（SPEC §5.4-2，勘误 E2）：总跨度恒等于 `hold_ms`。"""
    if sustain is None or not retrigger or hold_ms <= sustain:
        return [(start_ms, hold_ms)]
    count = math.ceil((hold_ms + gap) / (sustain + gap))
    budget = hold_ms - (count - 1) * gap
    base = budget // count
    remainder = budget - base * count
    segments: list[tuple[int, int]] = []
    cursor = start_ms
    for index in range(count):
        length = base + (remainder if index == count - 1 else 0)
        segments.append((cursor, length))
        cursor += length + gap
    return segments


def compile_plan(
    score: Score,
    instrument: Instrument,
    settings,
    *,
    speed: float = 1.0,
) -> Plan:
    """把曲谱编译成演奏计划；失败时抛 `PlanError`。"""
    params = dict(settings.playback)
    gap = int(params["note_gap_ms"])
    min_hold = int(params["min_hold_ms"])
    lead = int(params["modifier_lead_ms"])
    tail = int(params["modifier_tail_ms"])
    sustain = params.get("sustain_limit_ms")
    retrigger = bool(params.get("retrigger_long_notes", True))

    issues: list[Issue] = list(score.issues)

    if not instrument.verified:
        raise PlanError(
            [Issue("CP004", "error", "乐器配置未校准（verified: false），请先在「校准」页确认按键语义")]
        )
    if not any(note.pitch is not None for note in score.notes):
        raise PlanError([Issue("KQ010", "error", "曲谱内没有任何音符")])
    if score.tempo_bpm <= 0 or speed <= 0:
        raise PlanError([Issue("KQ003", "error", f"tempo/speed 必须为正数：tempo={score.tempo_bpm}, speed={speed}")])

    ms_per_beat = 60000.0 / (score.tempo_bpm * speed)

    # ── 1) 目标音高与指法 ───────────────────────────────────────────────
    errors: list[Issue] = []
    staged: list[tuple[Any, int, int, int, Fingering]] = []  # (note, start_ms, duration_ms, hold_ms, fingering)
    prefer: tuple[str, ...] = ()
    previous_end_ms: int | None = None
    for note in score.notes:
        if note.pitch is None:
            continue
        target = note.pitch + score.transpose
        fingering = find_fingering(instrument, target, prefer_buttons=prefer)
        if fingering is None:
            errors.append(
                Issue(
                    "CP001",
                    "error",
                    f"音高 {target:+d}（{note.repr}，第 {note.line} 行）超出乐器音域或缺少可用的修饰键组合",
                    line=note.line,
                )
            )
            continue
        prefer = fingering.buttons
        start_ms = round(note.start_beat * ms_per_beat)
        duration_ms = round(note.duration_beat * ms_per_beat)
        # 逐音独立取整可能让后一音早于前一音结束 1 ms（浮点误差）；这里强制首尾相接，杜绝重叠
        if previous_end_ms is not None and start_ms < previous_end_ms:
            start_ms = previous_end_ms
        previous_end_ms = start_ms + duration_ms
        staged.append((note, start_ms, duration_ms, _hold_ms(duration_ms, gap, min_hold), fingering))
    if errors:
        raise PlanError(errors)

    # ── 2) 连音合并（SPEC §5.4-1）────────────────────────────────────────
    playable: list[_PlayableNote] = []
    for note, start_ms, duration_ms, hold_ms, fingering in staged:
        previous = playable[-1] if playable else None
        if (
            note.tie
            and previous is not None
            and previous.pitch == note.pitch + score.transpose
            and previous.start_ms + previous.duration_ms == start_ms
        ):
            # 与前一音连成一口气：hold 累加（含本应断开的那段 gap）
            previous.duration_ms += duration_ms
            previous.hold_ms += gap + hold_ms
            continue
        entry = _PlayableNote(
            pitch=note.pitch + score.transpose,
            repr=note.repr,
            start_ms=start_ms,
            duration_ms=duration_ms,
            fingering=fingering,
            line=note.line,
            hold_ms=hold_ms,
        )
        playable.append(entry)

    # ── 3) 长音切分 → 段列表 ────────────────────────────────────────────
    segments: list[tuple[int, int, Fingering, int]] = []  # (start, hold, fingering, note_index)
    for index, entry in enumerate(playable):
        for seg_start, seg_hold in _split_segments(entry.start_ms, entry.hold_ms, sustain, retrigger, gap):
            segments.append((seg_start, seg_hold, entry.fingering, index))

    # ── 4) 修饰键状态机 + 事件生成（SPEC §5.4-3/4，勘误 E5/E6）──────────
    events: list[PlanEvent] = []
    held: tuple[str, ...] = ()
    shift = 0
    offset_ms = 0
    prev_key_up: int | None = None
    note_start: dict[int, int] = {}

    for order, (raw_start, hold_ms, fingering, note_index) in enumerate(segments):
        need = tuple(fingering.buttons)
        start_ms = raw_start + shift
        note_start.setdefault(note_index, start_ms)

        if need != held:
            release_at = prev_key_up + tail if prev_key_up is not None else None
            press_at = start_ms - lead
            required = release_at if release_at is not None else 0
            if press_at < required:
                delta = required - press_at
                shift += delta
                start_ms += delta
                press_at = required
                if release_at is not None:
                    issues.append(
                        Issue(
                            "CP002",
                            "warning",
                            f"第 {note_index + 1} 个音换修饰键时间不足，已顺延 {delta} ms",
                        )
                    )
            if release_at is not None:
                for button in held:
                    if button not in need:
                        events.append(PlanEvent(release_at, "mouse_up", button))
            for button in need:
                if button not in held:
                    events.append(PlanEvent(press_at, "mouse_down", button))
            held = need

        key_up_at = start_ms + hold_ms
        events.append(PlanEvent(start_ms, "key_down", fingering.key))
        events.append(PlanEvent(key_up_at, "key_up", fingering.key))
        prev_key_up = key_up_at
        if order == 0:
            offset_ms = shift

    if held and prev_key_up is not None:
        for button in held:
            events.append(PlanEvent(prev_key_up + tail, "mouse_up", button))

    # ── 5) 排序与不变量校验（SPEC §5.5）─────────────────────────────────
    events.sort(key=lambda event: event.t_ms)
    _check_invariants(events)

    plan_notes = tuple(
        PlanNote(
            index=index,
            start_ms=note_start.get(index, entry.start_ms),
            duration_ms=entry.duration_ms,
            pitch=entry.pitch,
            repr=entry.repr,
            fingering=entry.fingering,
        )
        for index, entry in enumerate(playable)
    )

    return Plan(
        version=1,
        title=score.title,
        tempo_bpm=score.tempo_bpm,
        speed=float(speed),
        transpose=score.transpose,
        source=score.source,
        generated_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        offset_ms=offset_ms,
        params=params,
        issues=tuple(issues),
        notes=plan_notes,
        events=tuple(events),
    )


def _check_invariants(events: list[PlanEvent]) -> None:
    """SPEC §5.5：时间非负、同键不重叠、结束时全部松开。"""
    pressed: set[str] = set()
    previous_time = -1
    for event in events:
        if event.t_ms < 0:
            raise PlanError([Issue("CP003", "error", f"事件时间为负：{event.t_ms} ms")])
        if event.t_ms < previous_time:
            raise PlanError([Issue("CP003", "error", "事件时间未按升序排列")])
        previous_time = event.t_ms
        if event.op.endswith("_down"):
            if event.arg in pressed:
                raise PlanError([Issue("CP003", "error", f"{event.arg} 在未松开时被再次按下")])
            pressed.add(event.arg)
        else:
            pressed.discard(event.arg)
    if pressed:
        raise PlanError([Issue("CP003", "error", f"计划结束时仍有按住的键：{sorted(pressed)}")])
