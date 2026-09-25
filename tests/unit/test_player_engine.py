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

    paused_count = len(sender.actions)
    time.sleep(0.15)
    assert len(sender.actions) == paused_count

    player.resume()
    assert player.state == "playing"
    wait_for_state(player, {"stopped", "idle"})
    assert len(sender.actions) > paused_count


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
        ("error", "idle"),
    }
    assert seen[0] == "idle"
    for previous, current in zip(seen, seen[1:]):
        assert (previous, current) in legal, f"非法状态迁移：{previous} → {current}"

