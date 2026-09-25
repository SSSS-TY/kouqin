"""乐器模型与音高映射（SPEC §3.1、§5.3）。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from kouqin.core.pitch import key_semitone, modifier_offset


@dataclass(frozen=True)
class KeyDef:
    key: str
    degree: int
    octave: int


@dataclass(frozen=True)
class ModifierDef:
    button: str
    label: str
    semitone: int


@dataclass(frozen=True)
class ModifierSet:
    buttons: tuple[str, ...]
    status: str
    note: str = ""


@dataclass(frozen=True)
class Fingering:
    """一次按键方案：按哪个键、需要同时按住哪些鼠标键。"""

    key: str
    buttons: tuple[str, ...]


@dataclass(frozen=True)
class Instrument:
    version: int
    verified: bool
    keys: tuple[KeyDef, ...]
    modifiers: tuple[ModifierDef, ...]
    modifier_sets: tuple[ModifierSet, ...]

    @property
    def key_order(self) -> dict[str, int]:
        return {key.key: index for index, key in enumerate(self.keys)}


def load_instrument(path: str | Path) -> Instrument:
    """读取 `config/instrument.json`（键位与乐器语义的唯一权威来源）。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return Instrument(
        version=int(data.get("version", 1)),
        verified=bool(data.get("verified", False)),
        keys=tuple(
            KeyDef(key=item["key"], degree=int(item["degree"]), octave=int(item["octave"]))
            for item in data.get("keys", [])
        ),
        modifiers=tuple(
            ModifierDef(button=item["button"], label=item.get("label", ""), semitone=int(item["semitone"]))
            for item in data.get("modifiers", [])
        ),
        modifier_sets=tuple(
            ModifierSet(
                buttons=tuple(item.get("buttons", [])),
                status=item.get("status", "assumed"),
                note=item.get("note", ""),
            )
            for item in data.get("modifier_sets", [])
        ),
    )


def usable_sets(instrument: Instrument) -> list[ModifierSet]:
    """只有 `verified` 的组合参与映射（SPEC §3.1）。"""
    return [entry for entry in instrument.modifier_sets if entry.status == "verified"]


def reachable(instrument: Instrument) -> set[int]:
    """所有可达音高（相对中音 1 的半音数）。"""
    offsets = [modifier_offset(entry.buttons, instrument.modifiers) for entry in usable_sets(instrument)]
    return {
        key_semitone(key) + offset
        for key in instrument.keys
        for offset in offsets
    }


def find_fingering(
    instrument: Instrument, target: int, prefer_buttons: Sequence[str] = ()
) -> Fingering | None:
    """按 SPEC §5.3 的优先级为 `target` 选一个指法；不可达时返回 `None`。

    优先级：① 只用 verified 组合；② 鼠标键数量更少；③ 与 `prefer_buttons` 相同；
    ④ 键位表顺序靠前。
    """
    candidates: list[tuple[str, tuple[str, ...]]] = []
    for entry in usable_sets(instrument):
        offset = modifier_offset(entry.buttons, instrument.modifiers)
        for key in instrument.keys:
            if key_semitone(key) + offset == target:
                candidates.append((key.key, entry.buttons))
    if not candidates:
        return None

    fewest = min(len(buttons) for _, buttons in candidates)
    candidates = [item for item in candidates if len(item[1]) == fewest]

    preferred = tuple(prefer_buttons)
    same = [item for item in candidates if item[1] == preferred]
    if same:
        candidates = same

    order = instrument.key_order
    key, buttons = min(candidates, key=lambda item: order[item[0]])
    return Fingering(key=key, buttons=buttons)

