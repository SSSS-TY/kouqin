"""P0 注入实验工具的离线测试：只验证纯逻辑（事件计划、按键跟踪、参数构造），不真的注入输入。"""

from __future__ import annotations

import pytest

from tools.p0_sendinput_demo import (
    INSTRUMENT_KEYS,
    KEYEVENTF_KEYUP,
    KEYEVENTF_SCANCODE,
    SCAN_CODES,
    Action,
    InputSender,
    make_key_input,
    make_mouse_input,
    main,
    plan_hold_sweep,
    plan_key,
    plan_modifier_compare,
    plan_mouse,
    plan_scale,
)


def test_scan_codes_cover_all_instrument_keys_with_distinct_codes() -> None:
    codes = [SCAN_CODES[key] for key in INSTRUMENT_KEYS]
    assert None not in codes
    assert len(set(codes)) == len(codes)


def test_make_key_input_uses_scancode_and_keyup_flag() -> None:
    down = make_key_input("z", up=False)
    assert down.type == 1  # INPUT_KEYBOARD
    assert down.ki.wScan == SCAN_CODES["z"]
    assert down.ki.dwFlags == KEYEVENTF_SCANCODE

    up = make_key_input("z", up=True)
    assert up.ki.dwFlags == KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP


def test_make_key_input_rejects_unknown_key() -> None:
    with pytest.raises(KeyError):
        make_key_input("q", up=False)


def test_make_mouse_input_flags_for_each_button() -> None:
    assert make_mouse_input("left", up=False).mi.dwFlags == 0x0002
    assert make_mouse_input("left", up=True).mi.dwFlags == 0x0004
    assert make_mouse_input("middle", up=False).mi.dwFlags == 0x0020
    assert make_mouse_input("right", up=True).mi.dwFlags == 0x0010
    with pytest.raises(KeyError):
        make_mouse_input("wheel", up=False)


def test_plan_key_produces_down_up_pairs_at_expected_times() -> None:
    events = plan_key("z", hold_ms=60, repeat=3, interval_ms=200)
    assert [(t, a.kind, a.name) for t, a in events] == [
        (0.0, "key_down", "z"),
        (60.0, "key_up", "z"),
        (260.0, "key_down", "z"),
        (320.0, "key_up", "z"),
        (520.0, "key_down", "z"),
        (580.0, "key_up", "z"),
    ]


def test_plan_scale_follows_instrument_key_order() -> None:
    events = plan_scale(INSTRUMENT_KEYS, hold_ms=100, interval_ms=50)
    played = [a.name for _, a in events if a.kind == "key_down"]
    assert played == list(INSTRUMENT_KEYS)


def test_plan_hold_sweep_keeps_each_duration() -> None:
    events = plan_hold_sweep("z", [20, 40, 80], gap_ms=1000)
    holds = [
        events[i + 1][0] - events[i][0]
        for i in range(0, len(events), 2)
    ]
    assert holds == [20, 40, 80]


def test_plan_modifier_compare_brackets_reference_with_candidates() -> None:
    events = plan_modifier_compare("right", rounds=1)
    kinds = [(t, a.kind, a.name) for t, a in events]

    # 参考音必须是「先按住鼠标键、再按 z」，并按相反顺序释放
    assert kinds[:4] == [
        (0.0, "mouse_down", "right"),
        (20.0, "key_down", "z"),
        (370.0, "key_up", "z"),
        (410.0, "mouse_up", "right"),
    ]
    # 参考音之后（鼠标键已松开）逐个弹 8 个普通键作为候选
    candidates = [name for t, kind, name in kinds if kind == "key_down" and t > 410.0]
    assert candidates == list(INSTRUMENT_KEYS)
    assert not any(kind == "mouse_down" and t > 410.0 for t, kind, _ in kinds)


@pytest.mark.parametrize(
    "events",
    [
        plan_key("z", 60, 3, 200),
        plan_scale(INSTRUMENT_KEYS, 100, 50),
        plan_hold_sweep("z", [20, 30, 40], 1500),
        plan_modifier_compare("middle", rounds=2),
        plan_mouse("left", 300, 3, 800),
    ],
)
def test_all_plans_are_sorted_and_non_negative(events) -> None:
    times = [t for t, _ in events]
    assert times == sorted(times)
    assert all(t >= 0 for t in times)
    assert all(a.kind in {"key_down", "key_up", "mouse_down", "mouse_up"} for _, a in events)


def test_sender_tracks_pressed_and_releases_everything() -> None:
    recorded: list[Action] = []
    sender = InputSender(emit=recorded.append)

    sender.execute(Action("key_down", "z"))
    sender.execute(Action("mouse_down", "right"))
    assert sender.pressed == {Action("key_down", "z"), Action("mouse_down", "right")}

    sender.execute(Action("key_up", "z"))
    assert sender.pressed == {Action("mouse_down", "right")}

    sender.release_all()
    assert sender.pressed == frozenset()
    assert recorded == [
        Action("key_down", "z"),
        Action("mouse_down", "right"),
        Action("key_up", "z"),
        Action("mouse_up", "right"),
    ]


def test_sender_ignores_keyup_for_key_never_pressed() -> None:
    sender = InputSender(emit=lambda _action: None)
    sender.execute(Action("key_up", "z"))
    assert sender.pressed == frozenset()


def test_dry_run_prints_plan_without_sending(capsys) -> None:
    exit_code = main(["--dry-run", "scale", "--repeat", "1"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "dry-run：共 16 个事件，未发送任何输入" in out
    assert "key_down" in out and "z" in out


def test_sustain_mode_plan_covers_all_default_durations(capsys) -> None:
    """P0-7 用：默认依次按住 2/4/6/8/10/12 秒，共 6 段 12 个事件。"""
    exit_code = main(["--dry-run", "--yes", "sustain"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "dry-run：共 12 个事件，未发送任何输入" in out
    assert "第 6 段：12 秒" in out
    assert "从第几段开始" in out


def test_sustain_mode_accepts_custom_durations(capsys) -> None:
    exit_code = main(["--dry-run", "--yes", "sustain", "--durations", "1000,3000"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "dry-run：共 4 个事件，未发送任何输入" in out
    assert "第 2 段：3 秒" in out
