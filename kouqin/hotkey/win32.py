"""全局热键注册与管理（SPEC §7）。

用 `RegisterHotKey` 注册；按键组合会被系统「吞掉」，不会传给游戏窗口，
因此 `Ctrl+Alt+P` 之类不会触发游戏内动作（这是用户 2026-09-25 确认过的前提）。
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from typing import Callable

WM_HOTKEY = 0x0312

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

_MOD_NAMES = {
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
}

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.RegisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT)
_user32.RegisterHotKey.restype = wintypes.BOOL
_user32.UnregisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int)
_user32.UnregisterHotKey.restype = wintypes.BOOL


class HotkeyError(ValueError):
    """组合键字符串非法。"""


def parse_combo(text: str) -> tuple[int, int]:
    """把 `Ctrl+Alt+P` 解析成 `(modifiers, virtual_key)`。"""
    parts = [part.strip() for part in text.split("+") if part.strip()]
    if len(parts) < 2:
        raise HotkeyError(f"组合键至少需要一个修饰键与一个主键：{text!r}")
    modifiers = 0
    for part in parts[:-1]:
        try:
            modifiers |= _MOD_NAMES[part.lower()]
        except KeyError:
            raise HotkeyError(f"未知的修饰键：{part!r}（可用 Ctrl/Alt/Shift/Win）") from None
    key = parts[-1].upper()
    if len(key) == 1 and key.isalnum():
        vk = ord(key)
    elif key.startswith("F") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x70 + int(key[1:]) - 1
    elif key == "SPACE":
        vk = 0x20
    else:
        raise HotkeyError(f"不支持的主键：{parts[-1]!r}（支持 A-Z / 0-9 / F1-F24 / Space）")
    return modifiers | MOD_NOREPEAT, vk


@dataclass
class _Registration:
    hotkey_id: int
    combo: str
    callback: Callable[[], None]


class HotkeyManager:
    """注册/注销全局热键，并把收到的 `WM_HOTKEY` 分发给回调。"""

    def __init__(self) -> None:
        self._registrations: dict[int, _Registration] = {}
        self._hwnd: int | None = None
        self._next_id = 0xA000

    @property
    def registered(self) -> list[str]:
        return [item.combo for item in self._registrations.values()]

    def register(self, hwnd: int, combo: str, callback: Callable[[], None]) -> bool:
        """注册一个热键；被别的程序占用时返回 False（不抛异常）。"""
        self._hwnd = hwnd
        modifiers, vk = parse_combo(combo)
        self._next_id += 1
        if not _user32.RegisterHotKey(wintypes.HWND(hwnd), self._next_id, modifiers, vk):
            return False
        self._registrations[self._next_id] = _Registration(self._next_id, combo, callback)
        return True

    def unregister_all(self) -> None:
        if self._hwnd is None:
            return
        for hotkey_id in list(self._registrations):
            _user32.UnregisterHotKey(wintypes.HWND(self._hwnd), hotkey_id)
            self._registrations.pop(hotkey_id, None)

    def handle_message(self, msg: int, wparam: int) -> bool:
        """在 Qt 的原生事件过滤里调用；命中已注册热键则执行回调并返回 True。"""
        if msg != WM_HOTKEY:
            return False
        registration = self._registrations.get(int(wparam))
        if registration is None:
            return False
        registration.callback()
        return True

