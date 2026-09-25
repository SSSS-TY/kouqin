"""播放设置 `config/settings.json` 的读写（SPEC §3.2）。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kouqin.core.score import WARNING, Issue

# 默认值与仓库中 config/settings.json 的取值保持一致（由测试 G-08 看守）
DEFAULT_PLAYBACK: dict[str, Any] = {
    "min_hold_ms": 40,
    "note_gap_ms": 30,
    "modifier_lead_ms": 10,
    "modifier_tail_ms": 10,
    "countdown_ms": 3000,
    "retrigger_long_notes": False,
    "sustain_limit_ms": 8000,
    "retrigger_gap_ms": 12,
    "pause_when_unfocused": True,
}

DEFAULT_HOTKEYS: dict[str, str] = {
    "toggle_play": "Ctrl+Alt+P",
    "pause_resume": "Ctrl+Alt+U",
    "panic_release": "Ctrl+Alt+K",
}

DEFAULT_MIDI: dict[str, Any] = {"reference_note": 60, "reference_semitone": 0}


@dataclass(frozen=True)
class Settings:
    playback: dict[str, Any]
    hotkeys: dict[str, str]
    midi: dict[str, Any]
    issues: tuple[Issue, ...] = ()


def load_settings(path: str | Path) -> Settings:
    """读取设置；缺失字段补默认值并给出 warning，未知字段忽略（向前兼容）。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    issues: list[Issue] = []

    playback, missing_playback = _merge(DEFAULT_PLAYBACK, data.get("playback"), "playback")
    hotkeys, missing_hotkeys = _merge(DEFAULT_HOTKEYS, data.get("hotkeys"), "hotkeys")
    midi, missing_midi = _merge(DEFAULT_MIDI, data.get("midi"), "midi")

    missing = missing_playback + missing_hotkeys + missing_midi
    if missing:
        issues.append(Issue("CFG001", WARNING, f"settings.json 缺少字段，已用默认值：{sorted(missing)}"))

    if isinstance(playback.get("sustain_limit_ms"), float):
        playback["sustain_limit_ms"] = int(playback["sustain_limit_ms"])

    return Settings(playback=playback, hotkeys=hotkeys, midi=midi, issues=tuple(issues))


def save_settings(settings: Settings, path: str | Path) -> None:
    """写回设置（只写三个已知区块，未知字段不会保留）。"""
    data = {
        "version": 1,
        "playback": dict(settings.playback),
        "hotkeys": dict(settings.hotkeys),
        "midi": dict(settings.midi),
    }
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _merge(defaults: dict, provided: Any, section: str) -> tuple[dict, list[str]]:
    merged = dict(defaults)
    if not isinstance(provided, dict):
        return merged, [f"{section}.{key}" for key in defaults]
    missing: list[str] = []
    for key in defaults:
        if key in provided:
            merged[key] = provided[key]
        else:
            missing.append(f"{section}.{key}")
    return merged, missing
