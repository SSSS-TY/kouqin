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
# 下面这几个必须显式声明签名：64 位下句柄是 64 位，若不声明 restype，
# ctypes 会按 32 位 int 处理并截断句柄，进而拿不到窗口的进程号。
_user32.GetForegroundWindow.argtypes = ()
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD
_user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
_user32.GetWindowTextW.restype = ctypes.c_int
_user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
_user32.GetClassNameW.restype = ctypes.c_int


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


# ── 前台窗口（焦点守卫）──────────────────────────────────────────────────────


def foreground_window() -> int:
    """当前前台窗口句柄（0 表示没有）。"""
    return int(_user32.GetForegroundWindow() or 0)


def window_pid(hwnd: int) -> int:
    """窗口所属的进程号（取不到时返回 0）。"""
    if not hwnd:
        return 0
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
    return int(pid.value)


def window_title(hwnd: int) -> str:
    """窗口标题（用于日志与提示）。"""
    if not hwnd:
        return ""
    buffer = ctypes.create_unicode_buffer(256)
    _user32.GetWindowTextW(wintypes.HWND(hwnd), buffer, 256)
    return buffer.value


def window_class(hwnd: int) -> str:
    """窗口类名（用于识别终端窗口）。"""
    if not hwnd:
        return ""
    buffer = ctypes.create_unicode_buffer(256)
    _user32.GetClassNameW(wintypes.HWND(hwnd), buffer, 256)
    return buffer.value


def current_process_id() -> int:
    return int(ctypes.windll.kernel32.GetCurrentProcessId())


class FocusGuard:
    """确保按键只发给「开始播放时处于前台的窗口」。

    游戏演奏场景下这是安全底线：一旦用户 Alt+Tab 或按 Win 键离开游戏，
    继续注入就会把 `z x c v` 之类的按键打进别的程序（聊天窗口、编辑器……）。
    """

    #: 终端/控制台窗口类名：把按键打进去只会得到一堆乱码，直接拒绝
    CONSOLE_CLASSES = frozenset(
        {"ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS", "mintty", "PseudoConsoleWindow"}
    )

    def __init__(self) -> None:
        self.target: int = 0
        self.target_title: str = ""

    def capture(self) -> str | None:
        """记录目标窗口。成功返回 `None`；失败返回给用户看的原因。

        拒绝的三种情况：前台是本程序自身、前台是终端窗口、取不到窗口信息。
        """
        hwnd = foreground_window()
        if not hwnd:
            self.target = 0
            return "拿不到前台窗口信息。"
        pid = window_pid(hwnd)
        if pid == 0:
            # 取不到进程号时宁可拒绝：否则会把本程序自己的窗口当成目标窗口，
            # 表现为「一切回游戏就报焦点离开」。
            self.target = 0
            return "拿不到前台窗口的进程信息。"
        if pid == current_process_id():
            self.target = 0
            return "当前前台窗口是本程序，按键会打到本程序上。"
        if window_class(hwnd) in self.CONSOLE_CLASSES:
            self.target = 0
            return "当前前台窗口是终端，按键会打到终端里。"
        self.target = hwnd
        self.target_title = window_title(hwnd)
        return None

    def ok(self) -> bool:
        """目标窗口是否仍是前台窗口。

        **尚未捕获目标窗口时返回 True（不拦截）**——倒计时阶段就是这种情况：
        那时还没锁定目标，若在这里返回 False，倒计时会被立刻中止，表现为「点了开始没反应」。
        """
        if not self.target:
            return True
        return foreground_window() == self.target

    def describe_mismatch(self) -> str:
        """焦点不在目标窗口时给出可诊断的说明（目标窗口 vs 当前前台）。"""
        current = foreground_window()
        return (
            f"目标窗口：{self.target_title or self.target}；"
            f"当前前台：{window_title(current) or current}"
        )
