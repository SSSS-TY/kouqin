"""测试公共设施：路径常量、固定参数、临时配置工厂、假注入器。

由 `tests/conftest.py` 转发注册（fixtures 对全部测试可见）。
注意：本文件**不得**在模块级 import `kouqin.*`，否则未实现的模块会让全部测试无法收集。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
FIXTURES = TESTS_DIR / "fixtures"
SCORES_DIR = FIXTURES / "scores"
MIDI_DIR = FIXTURES / "midi"
EXPECTED_DIR = FIXTURES / "expected"
CONFIG_DIR = REPO_ROOT / "config"

# 固定播放参数：与 config/settings.json 的 playback 保持一致，由 G-08 校验二者相同。
# 测试统一用这组固定值，避免用户日后调整配置造成大量用例噪声。
PINNED_PLAYBACK: dict[str, object] = {
    "min_hold_ms": 40,
    "note_gap_ms": 30,
    "modifier_lead_ms": 10,
    "modifier_tail_ms": 10,
    "countdown_ms": 3000,
    "retrigger_long_notes": True,
    "sustain_limit_ms": None,
}

PINNED_MIDI: dict[str, object] = {"reference_note": 60, "reference_semitone": 0}


def score_text(name: str) -> str:
    """读取 `tests/fixtures/scores/` 下的样例文本。"""
    return (SCORES_DIR / name).read_text(encoding="utf-8")


def write_settings(
    tmp_path: Path,
    *,
    playback: dict[str, object] | None = None,
    midi: dict[str, object] | None = None,
) -> Path:
    """写出一个临时 settings.json，返回其路径。"""
    data = {
        "version": 1,
        "playback": {**PINNED_PLAYBACK, **(playback or {})},
        "hotkeys": {
            "toggle_play": "Ctrl+Alt+P",
            "pause_resume": "Ctrl+Alt+U",
            "panic_release": "Ctrl+Alt+L",
        },
        "midi": {**PINNED_MIDI, **(midi or {})},
    }
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def shipped_instrument() -> dict:
    """读取仓库中实际的乐器配置（只读）。"""
    return json.loads((CONFIG_DIR / "instrument.json").read_text(encoding="utf-8"))


def shipped_settings() -> dict:
    """读取仓库中实际的播放设置（只读）。"""
    return json.loads((CONFIG_DIR / "settings.json").read_text(encoding="utf-8"))


def write_instrument(tmp_path: Path, data: dict, name: str = "instrument.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


@pytest.fixture
def settings_path(tmp_path: Path) -> Path:
    """默认的临时 settings.json（固定参数）。"""
    return write_settings(tmp_path)


class FakeSender:
    """记录式假注入器：替代真实 `SendInput`，用于引擎测试。"""

    def __init__(self) -> None:
        self.actions: list[tuple[float, str, str]] = []
        self.release_all_calls = 0

    def send(self, action) -> None:  # action 具备 kind / arg 属性
        self.actions.append((time.monotonic(), action.kind, action.arg))

    def release_all(self) -> None:
        self.release_all_calls += 1
        self.actions.append((time.monotonic(), "release_all", "*"))

    # ── 断言辅助 ──

    @property
    def kinds(self) -> list[str]:
        return [kind for _, kind, _ in self.actions]

    @property
    def targets(self) -> list[tuple[str, str]]:
        return [(kind, arg) for _, kind, arg in self.actions]

    def is_everything_released(self) -> bool:
        """最后一个 down 之后必须有对应 up，或至少一次 release_all。"""
        pressed: set[str] = set()
        for _, kind, arg in self.actions:
            if kind == "release_all":
                pressed.clear()
            elif kind.endswith("_down"):
                pressed.add(arg)
            elif kind.endswith("_up"):
                pressed.discard(arg)
        return not pressed


@pytest.fixture
def fake_sender() -> FakeSender:
    return FakeSender()

