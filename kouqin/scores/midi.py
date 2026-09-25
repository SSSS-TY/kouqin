"""MIDI（SMF 0/1）导入（SPEC §3.6）。

用**纯标准库**解析标准 MIDI 文件，不引入新依赖：
解析 → 合并各轨为单音线（同刻取最高音）→ 换算成「相对半音 + 拍」的曲谱模型。
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from kouqin.core.score import ERROR, INFO, Issue, Note, Score, ScoreError

MIN_SEMITONE = -12   # 低音 1
MAX_SEMITONE = 24    # 两点 1
DRUM_CHANNEL = 9     # MIDI 通道 10（索引 9）
DEFAULT_TEMPO_US = 500_000


@dataclass(frozen=True)
class MidiImportResult:
    score: Score
    dropped_notes: int
    issues: tuple[Issue, ...]


def import_midi(
    path: str | Path,
    reference_note: int = 60,
    reference_semitone: int = 0,
) -> MidiImportResult:
    """导入 MIDI 文件；结构性错误抛 `ScoreError`。"""
    path = Path(path)
    data = path.read_bytes()
    if len(data) < 14 or data[:4] != b"MThd":
        raise ScoreError([Issue("MD001", ERROR, f"不是有效的 MIDI 文件（缺少 MThd）：{path.name}")])

    fmt, track_count, division = struct.unpack(">HHH", data[8:14])
    if fmt not in (0, 1):
        raise ScoreError([Issue("MD002", ERROR, f"只支持 format 0/1，实际为 {fmt}")])
    if division & 0x8000:
        raise ScoreError([Issue("MD003", ERROR, "不支持 SMPTE 时间码（division 最高位为 1）")])
    if division == 0:
        raise ScoreError([Issue("MD003", ERROR, "division 为 0，无法换算拍")])

    tempo_us = DEFAULT_TEMPO_US
    raw_notes: list[tuple[int, int, int]] = []  # (start_tick, end_tick, midi_note)

    offset = 14
    track_index = 0
    while offset + 8 <= len(data) and track_index < max(track_count, 1):
        tag = data[offset : offset + 4]
        if tag != b"MTrk":
            break
        length = struct.unpack(">I", data[offset + 4 : offset + 8])[0]
        payload = data[offset + 8 : offset + 8 + length]
        offset += 8 + length
        track_index += 1

        found_tempo, notes = _parse_track(payload)
        if tempo_us == DEFAULT_TEMPO_US and found_tempo is not None:
            tempo_us = found_tempo
        raw_notes.extend(notes)

    if not raw_notes:
        raise ScoreError([Issue("MD004", ERROR, f"MIDI 内没有任何音符：{path.name}")])

    tempo_bpm = 60_000_000 / tempo_us
    selected, dropped = _to_monophonic(raw_notes)

    notes: list[Note] = []
    out_of_range: list[int] = []
    for start_tick, end_tick, midi_note in selected:
        semitone = midi_note - reference_note + reference_semitone
        if not MIN_SEMITONE <= semitone <= MAX_SEMITONE:
            out_of_range.append(semitone)
        notes.append(
            Note(
                start_beat=start_tick / division,
                duration_beat=max((end_tick - start_tick) / division, 1 / 64),
                pitch=semitone,
                repr=f"midi{midi_note}",
                tie=False,
                line=1,
            )
        )

    issues: list[Issue] = []
    if dropped:
        issues.append(Issue("MD006", INFO, f"和弦被降为单音：丢弃了 {dropped} 个同时发音"))
    if out_of_range:
        raise ScoreError(
            [
                Issue(
                    "MD005",
                    ERROR,
                    f"有 {len(out_of_range)} 个音超出乐器音域（{min(out_of_range)}…{max(out_of_range)} 半音）："
                    "可用整体移调把曲子挪进低音 1 到两点 1 的范围",
                )
            ]
        )

    score = Score(
        title=path.stem,
        tempo_bpm=tempo_bpm,
        meter="4/4",
        transpose=0,
        notes=tuple(notes),
        source=str(path),
        issues=(),
    )
    return MidiImportResult(score=score, dropped_notes=dropped, issues=tuple(issues))


def _parse_track(payload: bytes) -> tuple[int | None, list[tuple[int, int, int]]]:
    """解析一条轨道，返回 (首个 set_tempo, 音符列表[(start,end,note)])。"""
    position = 0
    tick = 0
    status: int | None = None
    tempo: int | None = None
    sounding: dict[tuple[int, int], int] = {}
    notes: list[tuple[int, int, int]] = []

    while position < len(payload):
        delta, position = _read_vlq(payload, position)
        tick += delta
        if position >= len(payload):
            break
        byte = payload[position]

        if byte == 0xFF:
            if position + 2 > len(payload):
                break
            meta_type = payload[position + 1]
            length, cursor = _read_vlq(payload, position + 2)
            body = payload[cursor : cursor + length]
            position = cursor + length
            if meta_type == 0x51 and len(body) >= 3 and tempo is None:
                tempo = int.from_bytes(body[:3], "big")
            elif meta_type == 0x2F:
                break
            continue

        if byte & 0x80:
            status = byte
            position += 1
        if status is None:
            break

        kind = status & 0xF0
        channel = status & 0x0F
        if kind in (0x80, 0x90):
            if position + 2 > len(payload):
                break
            note = payload[position]
            velocity = payload[position + 1]
            position += 2
            if channel == DRUM_CHANNEL:
                continue
            key = (channel, note)
            if kind == 0x90 and velocity > 0:
                sounding.setdefault(key, tick)
            else:
                start = sounding.pop(key, None)
                if start is not None:
                    notes.append((start, tick, note))
        elif kind in (0xA0, 0xB0, 0xE0):
            position += 2
        elif kind in (0xC0, 0xD0):
            position += 1
        else:
            break

    # 没有显式关音的音符：以轨道结尾收尾
    for (_, note), start in sounding.items():
        notes.append((start, tick, note))
    return tempo, notes


def _read_vlq(data: bytes, position: int) -> tuple[int, int]:
    value = 0
    while position < len(data):
        byte = data[position]
        position += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            break
    return value, position


def _to_monophonic(
    raw_notes: list[tuple[int, int, int]]
) -> tuple[list[tuple[int, int, int]], int]:
    """按起始时刻分组，同刻保留最高音；并裁掉与前音重叠的尾部。"""
    groups: dict[int, list[tuple[int, int]]] = {}
    for start, end, note in raw_notes:
        groups.setdefault(start, []).append((end, note))

    selected: list[tuple[int, int, int]] = []
    dropped = 0
    for start in sorted(groups):
        items = sorted(groups[start], key=lambda item: (-item[1], item[0]))
        end, note = items[0]
        dropped += len(items) - 1
        selected.append((start, end, note))

    for index in range(len(selected) - 1):
        start, end, note = selected[index]
        next_start = selected[index + 1][0]
        if end > next_start:
            selected[index] = (start, next_start, note)
    return selected, dropped

