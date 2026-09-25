"""热键解析的离线测试（SPEC §7）。不依赖桌面环境，纯逻辑。

顺带守住「配置里的默认热键必须能解析」——写错一个字母就会导致注册失败。
"""

from __future__ import annotations

import pytest

from kouqin.hotkey.win32 import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_NOREPEAT,
    MOD_SHIFT,
    HotkeyError,
    parse_combo,
)

from tests.helpers import shipped_settings


def test_parse_ctrl_alt_letter() -> None:
    assert parse_combo("Ctrl+Alt+P") == (MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, ord("P"))


def test_parse_is_case_insensitive_and_supports_function_keys() -> None:
    assert parse_combo("ctrl+shift+f12") == (MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, 0x7B)
    assert parse_combo("Win+Space") == (0x0008 | MOD_NOREPEAT, 0x20)


@pytest.mark.parametrize("combo", ["F8", "Ctrl+Alt", "", "Ctrl+Alt+F99", "Ctrl+Alt+?"])
def test_invalid_combos_are_rejected(combo: str) -> None:
    with pytest.raises(HotkeyError):
        parse_combo(combo)


def test_shipped_default_hotkeys_are_parsable_and_distinct() -> None:
    hotkeys = shipped_settings()["hotkeys"]
    parsed = {key: parse_combo(combo) for key, combo in hotkeys.items()}
    assert len(set(parsed.values())) == len(parsed), "默认热键之间存在重复"


def test_default_hotkeys_avoid_instrument_keys() -> None:
    """热键字母避开 z x c v b n m ,：万一注册失败也不会因此误发一个音。"""
    instrument_keys = set("zxcvbnm,")
    for combo in shipped_settings()["hotkeys"].values():
        main_key = combo.split("+")[-1].strip().lower()
        assert main_key not in instrument_keys, combo

