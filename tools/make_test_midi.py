"""生成测试用的 MIDI（SMF）样例文件。

产物写入 `tests/fixtures/midi/`，**确定性**生成（同样的输入每次都产生同样的字节），
因此可以入库，并由测试 `M-00` 比对「重新生成 == 入库文件」，防止素材被误改。

用法::

    python tools/make_test_midi.py            # 写入样例文件
    python tools/make_test_midi.py --check    # 只校验入库文件是否与生成结果一致

样例说明见 `docs/design/TEST_PLAN.md` §4。
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path
from typing import Iterable, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
MIDI_DIR = REPO_ROOT / "tests" / "fixtures" / "midi"

Event = tuple[int, bytes]  # (delta ticks, raw event bytes)


# ── 低层写入 ──────────────────────────────────────────────────────────────────


def vlq(value: int) -> bytes:
    """可变长度量（MIDI 的 delta time 编码）。"""
    if value < 0:
        raise ValueError("delta 不能为负")
    out = bytearray([value & 0x7F])
    value >>= 7
    while value:
        out.insert(0, (value & 0x7F) | 0x80)
        value >>= 7
    return bytes(out)


def chunk(tag: bytes, payload: bytes) -> bytes:
    return tag + struct.pack(">I", len(payload)) + payload


def header(fmt: int, ntrk: int, division: int) -> bytes:
    return chunk(b"MThd", struct.pack(">HHH", fmt, ntrk, division))


def track(events: Iterable[Event]) -> bytes:
    return chunk(b"MTrk", b"".join(vlq(delta) + data for delta, data in events))


def note_on(delta: int, channel: int, note: int, velocity: int = 64) -> Event:
    return delta, bytes([0x90 | channel, note, velocity])


def note_off(delta: int, channel: int, note: int) -> Event:
    return delta, bytes([0x80 | channel, note, 0])


def raw(delta: int, data: bytes) -> Event:
    """直接写入原始事件字节（用于 running status 等特殊构造）。"""
    return delta, data


TEMPO = b"\xFF\x51\x03"
TIME_SIG_4_4 = b"\xFF\x58\x04\x04\x02\x18\x08"
END_OF_TRACK = b"\xFF\x2F\x00"


def tempo(delta: int, usec_per_beat: int) -> Event:
    return delta, TEMPO + usec_per_beat.to_bytes(3, "big")


def end_of_track(delta: int = 0) -> Event:
    return delta, END_OF_TRACK


# ── 样例构建 ──────────────────────────────────────────────────────────────────


def build_sample_multi() -> bytes:
    """format 1：指挥轨（150 BPM）+ 旋律轨（含一处和弦）+ 低音轨 + 打击轨（须忽略）。

    合并后的单音线（s = midi − 60，division = 480）：
        tick 0    → beat 0.0, s = 0,   1 拍
        tick 480  → beat 1.0, s = 4,   1 拍
        tick 960  → beat 2.0, s = 11,  1 拍（67 与 71 同时按下，保留最高音，丢弃 1 个）
        tick 1440 → beat 3.0, s = 12,  1 拍
        tick 1920 → beat 4.0, s = -12, 1 拍（低音轨）
        tick 2400 → beat 5.0, s = -10, 1 拍
    """
    conductor = track([tempo(0, 400_000), raw(0, TIME_SIG_4_4), end_of_track()])

    melody = track(
        [
            note_on(0, 0, 60),
            note_off(480, 0, 60),
            note_on(0, 0, 64),
            note_off(480, 0, 64),
            note_on(0, 0, 67),
            note_on(0, 0, 71),
            note_off(480, 0, 67),
            note_off(0, 0, 71),
            note_on(0, 0, 72),
            note_off(480, 0, 72),
            end_of_track(),
        ]
    )

    bass = track(
        [
            note_on(1920, 1, 48),
            note_off(480, 1, 48),
            note_on(0, 1, 50),
            note_off(480, 1, 50),
            end_of_track(),
        ]
    )

    drums = track(
        [
            note_on(0, 9, 36),
            note_off(120, 9, 36),
            note_on(360, 9, 38),
            note_off(120, 9, 38),
            note_on(360, 9, 36),
            note_off(120, 9, 36),
            note_on(360, 9, 38),
            note_off(120, 9, 38),
            end_of_track(),
        ]
    )

    return header(1, 4, 480) + conductor + melody + bass + drums


def build_sample_format0() -> bytes:
    """format 0、无 tempo 元事件（→ 120 BPM）、使用 running status。

    期望：2 个音，(beat 0, s = 0) 与 (beat 1, s = 2)，各 1 拍。
    """
    return header(0, 1, 480) + track(
        [
            raw(0, bytes([0x90, 60, 64])),      # note on 60
            raw(480, bytes([60, 0])),           # running status → note on 60 vel 0 = 关音
            raw(0, bytes([62, 64])),            # running status → note on 62
            raw(480, bytes([62, 0])),
            end_of_track(),
        ]
    )


def build_out_of_range() -> bytes:
    """单个音 midi 90 → s = 30，超出乐器音域（应报 MD005）。"""
    return header(0, 1, 480) + track([note_on(0, 0, 90), note_off(480, 0, 90), end_of_track()])


def build_bad_format2() -> bytes:
    return header(2, 1, 480) + track([note_on(0, 0, 60), end_of_track(480)])


def build_bad_smpte() -> bytes:
    """division 最高位为 1 → SMPTE 时间码（应报 MD003）。"""
    return header(0, 1, 0xE728) + track([note_on(0, 0, 60), end_of_track(480)])


def build_no_notes() -> bytes:
    return header(0, 1, 480) + track([tempo(0, 500_000), raw(0, TIME_SIG_4_4), end_of_track()])


def build_not_midi() -> bytes:
    return b"THIS IS NOT A MIDI FILE\n" * 4


BUILDERS: dict[str, object] = {
    "sample_multi.mid": build_sample_multi,
    "sample_format0.mid": build_sample_format0,
    "out_of_range.mid": build_out_of_range,
    "bad_format2.mid": build_bad_format2,
    "bad_smpte.mid": build_bad_smpte,
    "no_notes.mid": build_no_notes,
    "not_midi.bin": build_not_midi,
}


def build_all() -> dict[str, bytes]:
    """返回 {文件名: 字节内容}，供脚本写入与测试比对。"""
    return {name: builder() for name, builder in BUILDERS.items()}  # type: ignore[operator]


def write_all(directory: Path = MIDI_DIR) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for name, payload in build_all().items():
        path = directory / name
        path.write_bytes(payload)
        written.append(path)
    return written


def check(directory: Path = MIDI_DIR) -> list[str]:
    """返回与入库文件不一致的文件名列表（空列表 = 一致）。"""
    problems = []
    for name, payload in build_all().items():
        path = directory / name
        if not path.is_file() or path.read_bytes() != payload:
            problems.append(name)
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成/校验测试用 MIDI 样例")
    parser.add_argument("--check", action="store_true", help="只校验，不写入")
    parser.add_argument("--dir", type=Path, default=MIDI_DIR, help="输出目录")
    args = parser.parse_args(argv)

    if args.check:
        problems = check(args.dir)
        if problems:
            print(f"与生成结果不一致：{problems}", file=sys.stderr)
            return 1
        print(f"全部一致（{len(BUILDERS)} 个文件）")
        return 0

    for path in write_all(args.dir):
        print(f"  {path.relative_to(REPO_ROOT)!s:<40} {path.stat().st_size:>5} B")
    print(f"已生成 {len(BUILDERS)} 个样例到 {args.dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

