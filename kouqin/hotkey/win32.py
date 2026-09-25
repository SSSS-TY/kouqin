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
    hwnd: int          # 0 表示注册到「当前线程的消息队列」


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
        if _user32.RegisterHotKey(wintypes.HWND(hwnd), self._next_id, modifiers, vk):
            self._registrations[self._next_id] = _Registration(self._next_id, combo, callback, hwnd)
            return True
        # 回退：注册到调用线程的消息队列（Qt 会以 windows_dispatcher_MSG 形式交给原生事件过滤器）。
        # 某些环境下窗口句柄不可用于热键注册（如无交互桌面），这条回退能让热键仍然可用。
        if hwnd and _user32.RegisterHotKey(wintypes.HWND(None), self._next_id, modifiers, vk):
            self._registrations[self._next_id] = _Registration(self._next_id, combo, callback, 0)
            return True
        return False

    def unregister_all(self) -> None:
        for hotkey_id, registration in list(self._registrations.items()):
            _user32.UnregisterHotKey(wintypes.HWND(registration.hwnd), hotkey_id)
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

    def probe(self, combo: str) -> tuple[bool, str]:
        """检测组合键是否**被别的程序**占用。

        关键点：本程序启动时已经注册了这几个热键，直接试注册会因为「自己占用自己」而误报 1409，
        所以先临时全部注销，检测完再把原来的注册原样恢复（id 与回调都不变）。
        """
        saved = list(self._registrations.values())
        self.unregister_all()
        try:
            available, reason = probe_combo(self._hwnd or 0, combo)
        finally:
            for registration in saved:
                modifiers, vk = parse_combo(registration.combo)
                if _user32.RegisterHotKey(
                    wintypes.HWND(registration.hwnd), registration.hotkey_id, modifiers, vk
                ):
                    self._registrations[registration.hotkey_id] = registration
        return available, reason


def probe_combo(hwnd: int, combo: str) -> tuple[bool, str]:
    """试注册一次并立刻注销，返回 `(是否可用, 说明)`。

    占用时 Windows 返回 1409（热键已注册）；返回值带上原因，界面才能区分
    「被别的程序占用」与「本环境无法注册」。
    """
    modifiers, vk = parse_combo(combo)
    hotkey_id = 0x7FFE
    ctypes.set_last_error(0)
    if _user32.RegisterHotKey(wintypes.HWND(hwnd), hotkey_id, modifiers, vk):
        _user32.UnregisterHotKey(wintypes.HWND(hwnd), hotkey_id)
        return True, "可用"
    code = ctypes.get_last_error()
    if code == 1409:
        return False, "已被其它程序占用"
    # 再试一次线程队列（与 register 的回退一致）
    if hwnd and _user32.RegisterHotKey(wintypes.HWND(None), hotkey_id, modifiers, vk):
        _user32.UnregisterHotKey(wintypes.HWND(None), hotkey_id)
        return True, "可用"
    return False, f"无法注册（{ctypes.FormatError(code).strip() or code}）"


def probe(hwnd: int, combo: str) -> tuple[bool, str]:
    """兼容别名，等价于 `probe_combo`。"""
    return probe_combo(hwnd, combo)

