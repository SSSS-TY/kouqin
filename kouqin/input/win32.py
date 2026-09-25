"""Windows `SendInput` 封装（SPEC §4、§6.4）。

只做两件事：把一次 `Action` 送进系统输入队列；以及把当前按下的键全部松开。
键盘一律使用**扫描码**（`KEYEVENTF_SCANCODE`）——2026-09-25 实测游戏只认这种。
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

# ── 常量 ──────────────────────────────────────────────────────────────────────

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040

BUTTON_FLAGS: dict[str, tuple[int, int]] = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}

SCAN_CODES: dict[str, int] = {
    "z": 0x2C,
    "x": 0x2D,
    "c": 0x2E,
    "v": 0x2F,
    "b": 0x30,
    "n": 0x31,
    "m": 0x32,
    ",": 0x33,
}


# ── Win32 结构体 ──────────────────────────────────────────────────────────────


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
_user32.SendInput.restype = wintypes.UINT


# ── 动作与注入 ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Action:
    """一次注入动作：`kind ∈ {key_down, key_up, mouse_down, mouse_up}`，`arg` 为键字符或鼠标键名。"""

    kind: str
    arg: str

    @property
    def is_down(self) -> bool:
        return self.kind.endswith("_down")


def make_key_input(key: str, up: bool) -> INPUT:
    try:
        scan = SCAN_CODES[key]
    except KeyError:
        raise KeyError(f"未登记的按键：{key!r}（口琴键位：{' '.join(SCAN_CODES)}）") from None
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if up else 0)
    return INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=0, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=None))


def make_mouse_input(button: str, up: bool) -> INPUT:
    try:
        down_flag, up_flag = BUTTON_FLAGS[button]
    except KeyError:
        raise KeyError(f"未知鼠标键：{button!r}（可用：left / middle / right）") from None
    return INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, 0, up_flag if up else down_flag, 0, None))


class InputSender:
    """真实注入器：把动作送进系统队列，并提供「全部松开」的兜底。"""

    def send(self, action: Action) -> None:
        item = (
            make_key_input(action.arg, up=action.kind == "key_up")
            if action.kind.startswith("key")
            else make_mouse_input(action.arg, up=action.kind == "mouse_up")
        )
        sent = _user32.SendInput(1, ctypes.byref(item), ctypes.sizeof(item))
        if sent != 1:
            raise OSError(f"SendInput 失败：{action.kind} {action.arg}（错误码 {ctypes.get_last_error()}）")

    def release_all(self) -> None:
        """松开全部口琴键与三个鼠标键（不关心它们当前是否按下；重复发是安全的）。"""
        for key in SCAN_CODES:
            _user32.SendInput(1, ctypes.byref(make_key_input(key, up=True)), ctypes.sizeof(INPUT))
        for button in BUTTON_FLAGS:
            _user32.SendInput(1, ctypes.byref(make_mouse_input(button, up=True)), ctypes.sizeof(INPUT))


# ── 环境诊断 ──────────────────────────────────────────────────────────────────


def is_elevated() -> bool:
    """当前进程是否以管理员身份运行。"""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def is_injectable() -> bool:
    """粗略判断「现在注入能不能到前台窗口」。

    已知的失败模式是权限不匹配：游戏以管理员运行、本程序不是 → Windows 的 UIPI 会拦下注入。
    判不出来时返回 True（乐观），避免误报挡住用户。
    """
    try:
        if is_elevated():
            return True
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:
            return True
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return True
        try:
            token = wintypes.HANDLE()
            if not ctypes.windll.advapi32.OpenProcessToken(handle, 0x0008, ctypes.byref(token)):
                return True
            try:
                elevated = wintypes.DWORD()
                size = wintypes.DWORD(ctypes.sizeof(elevated))
                ok = ctypes.windll.advapi32.GetTokenInformation(
                    token, 20, ctypes.byref(elevated), size, ctypes.byref(size)  # TokenElevation = 20
                )
                return True if not ok else not bool(elevated.value)
            finally:
                ctypes.windll.kernel32.CloseHandle(token)
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    except Exception:  # noqa: BLE001 —— 诊断失败不应影响功能
        return True

