"""音高换算：简谱音级 → 半音、键位 → 半音、修饰组合 → 半音（SPEC §3.1、§3.2）。"""

from __future__ import annotations

from typing import Iterable, Sequence

# 大调音阶：简谱音级 1..7 相对主音的半音数
DEGREE_SEMITONES: dict[int, int] = {1: 0, 2: 2, 3: 4, 4: 5, 5: 7, 6: 9, 7: 11}

# 一个八度内的半音 → (音级, 变化音)，用于把任意半音还原成简谱写法
_SEMITONE_TO_DEGREE: dict[int, tuple[int, int]] = {
    0: (1, 0),
    1: (1, +1),
    2: (2, 0),
    3: (2, +1),
    4: (3, 0),
    5: (4, 0),
    6: (4, +1),
    7: (5, 0),
    8: (5, +1),
    9: (6, 0),
    10: (6, +1),
    11: (7, 0),
}


def degree_semitone(degree: int) -> int:
    """简谱音级（1–7）相对主音的半音数。"""
    try:
        return DEGREE_SEMITONES[degree]
    except KeyError:
        raise ValueError(f"非法音级：{degree!r}（应为 1–7）") from None


def key_semitone(key) -> int:
    """一个键位在无修饰键时发出的音高（相对中音 1 的半音数）。"""
    return degree_semitone(key.degree) + 12 * key.octave


def modifier_offset(buttons: Sequence[str], modifiers: Iterable) -> int:
    """修饰组合的偏移 = 各修饰键偏移之和（实测可叠加，SPEC §3.1）。"""
    by_button = {m.button: m.semitone for m in modifiers}
    total = 0
    for button in buttons:
        try:
            total += by_button[button]
        except KeyError:
            raise ValueError(f"未知修饰键：{button!r}") from None
    return total


def split_pitch(pitch: int) -> tuple[int, int, int]:
    """把半音数拆成 `(音级, 变化音, 八度)`，用于把任意半音写成简谱文本。"""
    octave, remainder = divmod(pitch, 12)
    degree, accidental = _SEMITONE_TO_DEGREE[remainder]
    return degree, accidental, octave

