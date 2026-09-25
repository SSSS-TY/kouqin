"""E-01…E-09：播放引擎与注入（SPEC §6）。

用真实时钟 + 极短计划 + 假 Sender；只断言事件顺序、状态与释放安全，不断言精确时刻。
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from kouqin.core.compile import compile_plan
from kouqin.core.instrument import load_instrument
from kouqin.player.engine import Player
from kouqin.scores.kq import parse_kq
from kouqin.settings import load_settings

from tests.helpers import FakeSender, shipped_instrument, write_instrument, write_settings

SHORT_SCORE = "@tempo 600\n\n1__ 1__ 1__ 1__"      # 4 × 25 ms = 100 ms
LONG_SCORE = "@tempo 600\n\n" + "1__ " * 40        # 40 × 25 ms ≈ 1000 ms


def build_player(tmp_path: Path, sender, text: str, **kwargs) -> Player:
    instrument = load_instrument(write_instrument(tmp_path, shipped_instrument()))
    settings = load_settings(write_settings(tmp_path, playback={"countdown_ms": 0}))
    plan = compile_plan(parse_kq(text), instrument, settings)
    return Player(plan, sender=sender, countdown_ms=0, **kwargs)


def wait_for_state(player, states: set[str], timeout: float = 2.0) -> str:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if player.state in states:
            return player.state
        time.sleep(0.002)
    raise AssertionError(f"等待状态 {states} 超时，当前为 {player.state!r}")


def test_e01_short_plan_runs_every_event_in_order(tmp_path: Path) -> None:
    sender = FakeSender()
    player = build_player(tmp_path, sender, SHORT_SCORE)
    player.play()
    wait_for_state(player, {"stopped", "idle"})

    assert sender.kinds == [
        "key_down",
        "key_up",
        "key_down",
        "key_up",
        "key_down",
        "key_up",
        "key_down",
        "key_up",
    ]
    assert sender.is_everything_released()


def test_e02_stop_halts_remaining_events_and_releases(tmp_path: Path) -> None:
    sender = FakeSender()
    player = build_player(tmp_path, sender, LONG_SCORE)
    player.play()
    time.sleep(0.06)
    player.stop()
    count_after_stop = len(sender.actions)

    time.sleep(0.2)
    assert len(sender.actions) == count_after_stop
    assert sender.is_everything_released()
    assert player.state in {"stopped", "idle"}


def test_e03_panic_releases_within_100ms(tmp_path: Path) -> None:
    sender = FakeSender()
    player = build_player(tmp_path, sender, LONG_SCORE)
    player.play()
    time.sleep(0.06)

    started = time.perf_counter()
    player.panic()
    while not sender.is_everything_released():
        assert time.perf_counter() - started < 0.1, "panic 后 100 ms 内未能释放全部按键"
        time.sleep(0.001)

    assert time.perf_counter() - started < 0.1
    assert player.state == "idle"


class RaisingSender(FakeSender):
    """在第 3 次发送时抛错，用于验证错误路径也要释放按键。"""

    def send(self, action) -> None:
        if len(self.actions) >= 2:
            raise OSError("模拟注入失败")
        super().send(action)


def test_e04_injection_error_enters_error_state_and_releases(tmp_path: Path) -> None:
    sender = RaisingSender()
    player = build_player(tmp_path, sender, LONG_SCORE)
    player.play()
    wait_for_state(player, {"error"}, timeout=1.0)
    assert sender.is_everything_released()


def test_e05_pause_then_resume(tmp_path: Path) -> None:
    sender = FakeSender()
    player = build_player(tmp_path, sender, LONG_SCORE)
    player.play()
    time.sleep(0.06)
    player.pause()
    assert player.state == "paused"

    time.sleep(0.05)  # 让 Player 线程完成「松开按下的键」
    paused_count = len(sender.actions)
    time.sleep(0.15)
    assert len(sender.actions) == paused_count, "暂停期间不应再发出任何事件"

    player.resume()
    assert player.state == "playing"
    wait_for_state(player, {"stopped", "idle"})
    assert len(sender.actions) > paused_count


def test_e14_pause_releases_held_key_and_resume_presses_it_back(tmp_path: Path) -> None:
    """暂停 = 静音：停在音符中间时必须松开按键，否则游戏里会一直响（用户实测的「变成长按」）。"""
    sender = FakeSender()
    # 单音 400 ms：确保暂停时正处在「键已按下、还没松开」的窗口内
    player = build_player(tmp_path, sender, "@tempo 600\n\n1----")
    player.play()
    time.sleep(0.05)
    player.pause()
    time.sleep(0.05)

    kinds = sender.kinds
    assert kinds.count("key_down") == 1
    assert kinds.count("key_up") == 1, "暂停时应松开按住的键"
    assert sender.is_everything_released()

    player.resume()
    time.sleep(0.1)
    assert sender.kinds.count("key_down") == 2, "恢复时应重新按下"

    player.stop()
    assert sender.is_everything_released()


def test_e06_replay_starts_from_beginning(tmp_path: Path) -> None:
    sender = FakeSender()
    player = build_player(tmp_path, sender, SHORT_SCORE)
    player.play()
    wait_for_state(player, {"stopped", "idle"})
    first_round = len(sender.actions)

    player.play()
    wait_for_state(player, {"stopped", "idle"})
    assert len(sender.actions) == first_round * 2


def test_e07_loop_mode_repeats_and_counts(tmp_path: Path) -> None:
    sender = FakeSender()
    player = build_player(tmp_path, sender, SHORT_SCORE, loop=True)
    player.play()

    deadline = time.perf_counter() + 2.0
    while player.loop_count < 2 and time.perf_counter() < deadline:
        time.sleep(0.005)

    player.stop()
    assert player.loop_count >= 2
    assert sender.is_everything_released()


def test_e08_shutdown_releases_everything(tmp_path: Path) -> None:
    sender = FakeSender()
    player = build_player(tmp_path, sender, LONG_SCORE)
    player.play()
    time.sleep(0.06)
    player.shutdown()

    assert sender.release_all_calls >= 1
    assert sender.is_everything_released()
    assert player.state in {"idle", "stopped"}


def test_e09_state_transitions_follow_the_state_machine(tmp_path: Path) -> None:
    sender = FakeSender()
    seen: list[str] = []
    instrument = load_instrument(write_instrument(tmp_path, shipped_instrument()))
    settings = load_settings(write_settings(tmp_path, playback={"countdown_ms": 0}))
    plan = compile_plan(parse_kq(SHORT_SCORE), instrument, settings)
    player = Player(plan, sender=sender, countdown_ms=0, on_state=seen.append)

    player.play()
    wait_for_state(player, {"stopped", "idle"})

    legal = {
        ("idle", "countdown"),
        ("idle", "playing"),
        ("countdown", "playing"),
        ("playing", "paused"),
        ("paused", "playing"),
        ("playing", "stopped"),
        ("playing", "idle"),
        ("paused", "stopped"),
        ("stopped", "idle"),
        ("stopped", "countdown"),
        ("stopped", "playing"),
        ("idle", "stopped"),
        ("playing", "error"),
        ("playing", "unfocused"),
        ("error", "idle"),
    }
    assert seen[0] == "idle"
    for previous, current in zip(seen, seen[1:]):
        assert (previous, current) in legal, f"非法状态迁移：{previous} → {current}"


class FakeGuard:
    """焦点守卫替身：`capture_problem` 控制能否开始，`ok_flag` 控制播放中是否仍在目标窗口。"""

    def __init__(self, capture_problem: str | None = None, ok_flag: bool = True) -> None:
        self.capture_problem = capture_problem
        self.ok_flag = ok_flag

    def capture(self) -> str | None:
        return self.capture_problem

    def ok(self) -> bool:
        return self.ok_flag


def test_e10_refuses_to_start_when_own_window_is_focused(tmp_path: Path) -> None:
    """前台还是本程序时拒绝开始——否则 z/x/c 会被打进本程序或别的窗口。"""
    sender = FakeSender()
    player = build_player(
        tmp_path, sender, SHORT_SCORE, focus_guard=FakeGuard(capture_problem="当前前台窗口是本程序。")
    )
    player.play()
    wait_for_state(player, {"error"})

    assert "本程序" in (player.last_error or "")
    # 只允许一次防御性 release_all；不得发出任何按下事件
    assert not any(kind.endswith("_down") for _, kind, _ in sender.actions)


def test_e11_stops_and_releases_when_focus_leaves_target(tmp_path: Path) -> None:
    """播放中焦点离开目标窗口（Alt+Tab / Win 键）→ 立即停止并释放所有按键。"""
    guard = FakeGuard()
    sender = FakeSender()
    player = build_player(tmp_path, sender, LONG_SCORE, focus_guard=guard, focus_grace_s=0.05)
    player.play()
    time.sleep(0.06)
    assert player.state == "playing"

    guard.ok_flag = False
    wait_for_state(player, {"unfocused"}, timeout=1.0)

    assert sender.is_everything_released()
    assert "焦点" in (player.last_message or "")


def test_e13_focus_flap_within_grace_keeps_playing(tmp_path: Path) -> None:
    """Alt+Tab 切换过程中焦点会短暂抖动：只要在宽限期内切回来，就继续演奏。"""
    guard = FakeGuard()
    sender = FakeSender()
    player = build_player(tmp_path, sender, LONG_SCORE, focus_guard=guard, focus_grace_s=0.6)
    player.play()
    time.sleep(0.06)

    guard.ok_flag = False
    time.sleep(0.1)
    guard.ok_flag = True
    time.sleep(0.2)

    assert player.state == "playing", "宽限期内切回来不应中止演奏"
    player.stop()


def test_e12_countdown_with_real_focus_guard_still_plays(tmp_path: Path, monkeypatch) -> None:
    """回归：带焦点守卫 + 倒计时时，必须能正常开始（用户报过「点了开始没反应」）。

    用的守卫是真实实现（只把 Win32 调用换成替身），覆盖「锁定目标 → 倒计时 → 播放」整条路径。
    """
    from kouqin.input import win32 as w

    monkeypatch.setattr(w, "foreground_window", lambda: 777)
    monkeypatch.setattr(w, "window_pid", lambda hwnd: 1234)
    monkeypatch.setattr(w, "current_process_id", lambda: 4321)
    monkeypatch.setattr(w, "window_class", lambda hwnd: "GameWindowClass")
    monkeypatch.setattr(w, "window_title", lambda hwnd: "游戏窗口")

    instrument = load_instrument(write_instrument(tmp_path, shipped_instrument()))
    settings = load_settings(write_settings(tmp_path, playback={"countdown_ms": 0}))
    plan = compile_plan(parse_kq(SHORT_SCORE), instrument, settings)
    sender = FakeSender()
    player = Player(plan, sender=sender, countdown_ms=50, focus_guard=w.FocusGuard())

    player.play()
    wait_for_state(player, {"stopped", "idle"})

    assert sender.kinds.count("key_down") == 4, "倒计时结束后应完整演奏 4 个音"
    assert player.state == "stopped"
