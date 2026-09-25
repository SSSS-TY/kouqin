"""焦点守卫的离线测试（SPEC §6.5）。

这里的**第一条**用例专门守住本次回归：守卫在「还没锁定目标窗口」时（倒计时阶段）
必须不拦截——否则倒计时会被立即中止，表现为「点了开始没反应」。
Win32 调用用 monkeypatch 替身，不需要真实桌面。
"""

from __future__ import annotations

import pytest

from kouqin.input import win32 as w


@pytest.fixture
def fake_windows(monkeypatch):
    """把前台窗口相关调用替换成可控的替身。"""

    class Fake:
        def __init__(self) -> None:
            self.foreground = 1000
            self.pid = 4242
            self.own_pid = 9999
            self.class_name = "GameWindowClass"
            self.title = "游戏窗口"

        def install(self) -> None:
            monkeypatch.setattr(w, "foreground_window", lambda: self.foreground)
            monkeypatch.setattr(w, "window_pid", lambda hwnd: self.pid)
            monkeypatch.setattr(w, "current_process_id", lambda: self.own_pid)
            monkeypatch.setattr(w, "window_class", lambda hwnd: self.class_name)
            monkeypatch.setattr(w, "window_title", lambda hwnd: self.title)

    fake = Fake()
    fake.install()
    return fake


def test_unlocked_guard_never_blocks(fake_windows) -> None:
    """回归：未锁定目标窗口时（倒计时阶段）不得拦截。"""
    guard = w.FocusGuard()
    assert guard.ok() is True
    fake_windows.foreground = 4321  # 前台随便变化也不该拦截
    assert guard.ok() is True


def test_capture_accepts_other_application(fake_windows) -> None:
    guard = w.FocusGuard()
    assert guard.capture() is None
    assert guard.target == 1000
    assert guard.target_title == "游戏窗口"
    assert guard.ok() is True


def test_capture_rejects_own_window(fake_windows) -> None:
    fake_windows.pid = fake_windows.own_pid
    guard = w.FocusGuard()
    problem = guard.capture()
    assert problem and "本程序" in problem
    assert guard.target == 0
    assert guard.ok() is True  # 没锁定 → 仍不拦截（由调用方决定是否继续）


def test_capture_rejects_console_window(fake_windows) -> None:
    fake_windows.class_name = "ConsoleWindowClass"
    guard = w.FocusGuard()
    problem = guard.capture()
    assert problem and "终端" in problem
    assert guard.target == 0


def test_capture_refuses_when_process_id_unknown(fake_windows) -> None:
    """取不到进程号时宁可拒绝：否则会把本程序自己的窗口当成目标（曾导致「一切回游戏就报焦点离开」）。"""
    fake_windows.pid = 0
    guard = w.FocusGuard()
    problem = guard.capture()
    assert problem and "进程" in problem
    assert guard.target == 0


def test_blocks_after_focus_moves_away(fake_windows) -> None:
    guard = w.FocusGuard()
    assert guard.capture() is None
    fake_windows.foreground = 1234  # 用户 Alt+Tab 走了
    assert guard.ok() is False
    fake_windows.foreground = 1000  # 切回来
    assert guard.ok() is True
