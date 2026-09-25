"""播放引擎（SPEC §6）。

专用线程执行计划；UI 线程只通过 `play/pause/resume/stop/panic/shutdown` 与进度回调交互。
停止与急停都保证「不留按下的键」，且等待期间每 ≤2 ms 检查一次中断标志（急停 ≤100 ms）。
"""

from __future__ import annotations

import threading
import time
from typing import Callable

from kouqin.input.win32 import Action

POLL_INTERVAL_S = 0.002

#: 鼠标修饰键名（暂停时只松开「发声音」的键，修饰键保持按住以免复音时音高出错）
BUTTON_NAMES = frozenset({"left", "middle", "right"})


class Player:
    """播放计划。`sender` 需实现 `send(action)` 与 `release_all()`（测试用假注入器）。"""

    def __init__(
        self,
        plan,
        *,
        sender,
        on_progress: Callable[[int, int], None] | None = None,
        on_state: Callable[[str], None] | None = None,
        loop: bool = False,
        countdown_ms: int = 0,
        focus_guard=None,
        focus_check_interval_s: float = 0.05,
        focus_grace_s: float = 1.2,
    ) -> None:
        self._plan = plan
        self._sender = sender
        self._on_progress = on_progress
        self._on_state = on_state
        self.loop = loop
        self._countdown_ms = countdown_ms
        self._focus_guard = focus_guard
        self._focus_interval = focus_check_interval_s
        self._focus_grace = focus_grace_s
        self._next_focus_check = 0.0

        self._state = "idle"
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._panic_event = threading.Event()
        self._pause_event = threading.Event()
        self._pressed: set[str] = set()
        self._epoch = 0.0
        self._note_index_of_event = self._build_note_index_map()
        self._total_notes = len(plan.notes)
        self.loop_count = 0
        self.last_error: str | None = None
        self.last_message: str | None = None

        if self._on_state is not None:
            self._on_state("idle")

    # ── 对外接口 ──

    @property
    def state(self) -> str:
        return self._state

    def play(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._panic_event.clear()
        self._pause_event.clear()
        self.loop_count = 0
        self.last_error = None
        self._thread = threading.Thread(target=self._run, name="kouqin-player", daemon=True)
        self._thread.start()

    def pause(self) -> None:
        if self._state == "playing":
            self._pause_event.set()
            self._set_state("paused")

    def resume(self) -> None:
        if self._pause_event.is_set():
            self._pause_event.clear()
            self._set_state("playing")

    def stop(self) -> None:
        self._stop_event.set()
        self._join()

    def panic(self) -> None:
        """急停：立刻停播并松开所有键。"""
        self._panic_event.set()
        self._join()

    def shutdown(self) -> None:
        """退出前调用：停播并强制释放所有键（幂等）。"""
        self._stop_event.set()
        self._join()
        self._release_all(force=True)
        if self._state != "error":
            self._set_state("idle")

    # ── 内部实现 ──

    def _join(self, timeout: float = 1.0) -> None:
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)

    def _set_state(self, state: str) -> None:
        self._state = state
        if self._on_state is not None:
            self._on_state(state)

    def _run(self) -> None:
        aborted = False
        try:
            if self._countdown_ms > 0:
                self._set_state("countdown")
                self._epoch = time.perf_counter()
                if not self._wait_until(self._epoch + self._countdown_ms / 1000.0):
                    aborted = True
            while not aborted:
                self._set_state("playing")
                aborted = not self._play_once()
                self.loop_count += 1
                if aborted or not self.loop:
                    break
        except OSError as exc:
            self.last_error = str(exc)
            self._set_state("error")
            self._release_all(force=True)
            return
        finally:
            self._release_all(force=aborted)
            if self._state in {"error", "unfocused"}:
                pass  # 保留具体原因，别覆盖成通用的完成/空闲
            elif aborted:
                self._set_state("idle")
            else:
                self._set_state("stopped")

    def _play_once(self) -> bool:
        """执行一遍计划；被中断时返回 False。"""
        if self._focus_guard is not None:
            # 焦点守卫：只把按键发给「开始播放时处于前台的窗口」。
            # 若前台仍是本程序（用户没切回游戏），直接拒绝开始——否则会把 z/x/c 打进本程序或别的窗口。
            self._next_focus_check = 0.0
            problem = self._focus_guard.capture()
            if problem:
                self.last_error = (
                    f"{problem}\n请先切换到游戏窗口，再按「开始」（或按 Ctrl+Alt+P）。\n"
                    "若判断有误、或不想启用这层保护，可在「设置 → 播放参数」里取消「焦点守卫」。"
                )
                self._set_state("error")
                return False
        self._epoch = time.perf_counter()
        for index, event in enumerate(self._plan.events):
            if not self._wait_until(self._epoch + event.t_ms / 1000.0):
                return False
            self._sender.send(Action(kind=event.op, arg=event.arg))
            if event.op.endswith("_down"):
                self._pressed.add(event.arg)
            else:
                self._pressed.discard(event.arg)
            if event.op == "key_up" and self._on_progress is not None:
                self._on_progress(self._note_index_of_event[index], self._total_notes)
        # 一遍结束：等到最后一个事件之后再返回
        return True

    def _wait_until(self, deadline: float) -> bool:
        """睡到 `deadline`，期间响应暂停/停止/急停；被中断返回 False。"""
        while True:
            if self._stop_event.is_set() or self._panic_event.is_set():
                return False
            if self._focus_guard is not None:
                now = time.perf_counter()
                if now >= self._next_focus_check:
                    self._next_focus_check = now + self._focus_interval
                    if not self._focus_guard.ok():
                        if self._await_focus_return():
                            continue
                        detail = getattr(self._focus_guard, "describe_mismatch", lambda: "")()
                        self.last_message = (
                            "焦点离开了目标窗口，已停止演奏并释放所有按键"
                            + (f"（{detail}）" if detail else "")
                            + "\n若不需要这层保护，可在「设置 → 播放参数」里取消「焦点守卫」。"
                        )
                        self._set_state("unfocused")
                        return False
            if self._pause_event.is_set():
                self._set_state("paused")
                # 暂停 = 静音：把当前按住的键松开，否则游戏里会一直响（表现为「变成长按」）
                paused_keys = self._release_keys_for_pause()
                paused_at = time.perf_counter()
                while self._pause_event.is_set():
                    if self._stop_event.is_set() or self._panic_event.is_set():
                        return False
                    time.sleep(POLL_INTERVAL_S)
                self._epoch += time.perf_counter() - paused_at
                self._repress_keys(paused_keys)
                self._set_state("playing")
                continue
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                return True
            time.sleep(min(remaining, POLL_INTERVAL_S))

    def _release_all(self, *, force: bool) -> None:
        if force or self._pressed:
            self._sender.release_all()
        self._pressed.clear()

    def _release_keys_for_pause(self) -> list[str]:
        """暂停时松开所有「发声键」（保留鼠标修饰键，避免恢复时音高先于修饰键生效）。"""
        keys = [arg for arg in sorted(self._pressed) if arg not in BUTTON_NAMES]
        for key in keys:
            self._sender.send(Action("key_up", key))
            self._pressed.discard(key)
        return keys

    def _repress_keys(self, keys: list[str]) -> None:
        """恢复时把暂停时松开的键重新按下；剩余时值由冻结的时钟保证。"""
        for key in keys:
            self._sender.send(Action("key_down", key))
            self._pressed.add(key)

    def _await_focus_return(self) -> bool:
        """焦点短暂离开（例如 Alt+Tab 切换过程中）时给一点宽限：切回来就继续演奏。"""
        started = time.perf_counter()
        deadline = started + self._focus_grace
        while time.perf_counter() < deadline:
            if self._stop_event.is_set() or self._panic_event.is_set():
                return False
            if self._focus_guard.ok():
                self._epoch += time.perf_counter() - started  # 补回等待时间，别把音乐跳过去
                return True
            time.sleep(0.02)
        return False

    def _build_note_index_map(self) -> list[int]:
        """给每个事件标注它属于哪个音（用于进度回调）。"""
        starts = {note.start_ms: note.index for note in self._plan.notes}
        mapping: list[int] = []
        current = 0
        for event in self._plan.events:
            if event.t_ms in starts:
                current = starts[event.t_ms]
            mapping.append(current)
        return mapping
