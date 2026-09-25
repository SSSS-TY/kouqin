"""P0 实验工具：纯 Python（ctypes + SendInput）向游戏注入键盘/鼠标输入。

目的：验证《三角洲行动》是否接受 Python 侧注入的输入，并测量按键最短可按时长。
结论回填 `docs/harness/PROGRESS.md` 的 P0-2 / P0-3，并据此决定 ADR-001 的运行时路线。

用法示例::

    python tools/p0_sendinput_demo.py check                    # 环境自检（管理员/前台窗口）
    python tools/p0_sendinput_demo.py scale                    # 依次弹 z x c v b n m ,
    python tools/p0_sendinput_demo.py key --key z --repeat 5   # 同一键连弹 5 次
    python tools/p0_sendinput_demo.py hold-sweep               # 不同按时长对比（测最短可按时长）
    python tools/p0_sendinput_demo.py compare --button right   # 标定「降调/半音/升调」是几半音
    python tools/p0_sendinput_demo.py mouse --button left      # 只测鼠标键注入是否生效

安全约定：只发送口琴所需的按键与鼠标按键；不移动鼠标、不读写游戏内存、不常驻、不连发。
所有模式都会在退出时释放仍然按下的键（含 Ctrl+C 与异常路径）。
"""

from __future__ import annotations

import argparse
import atexit
import ctypes
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass
from typing import Callable, Sequence

# ── SendInput 常量 ────────────────────────────────────────────────────────────

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

# 键盘扫描码（Set 1）。游戏通常只认扫描码，因此一律带 KEYEVENTF_SCANCODE。
SCAN_CODES: dict[str, int] = {
    # 口琴键位（用户口述）
    "z": 0x2C,
    "x": 0x2D,
    "c": 0x2E,
    "v": 0x2F,
    "b": 0x30,
    "n": 0x31,
    "m": 0x32,
    ",": 0x33,
    # 以下仅用于排查（不属于口琴键位）
    "a": 0x1E,
    "s": 0x1F,
    "d": 0x20,
    "f": 0x21,
    "g": 0x22,
    "1": 0x02,
    "2": 0x03,
    "3": 0x04,
    "escape": 0x01,
    "space": 0x39,
}

INSTRUMENT_KEYS: tuple[str, ...] = ("z", "x", "c", "v", "b", "n", "m", ",")

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
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
_user32.SendInput.restype = wintypes.UINT

# ── 动作与计划（纯逻辑，可离线测试）──────────────────────────────────────────


@dataclass(frozen=True)
class Action:
    """一次注入动作：`kind` ∈ {key_down, key_up, mouse_down, mouse_up}，`name` 为键字符或鼠标键名。"""

    kind: str
    name: str

    @property
    def is_down(self) -> bool:
        return self.kind.endswith("_down")


Event = tuple[float, Action]  # (相对时间毫秒, 动作)


def plan_sequence(items: Sequence[tuple[str, float]], interval_ms: float) -> list[Event]:
    """把 `(键, 按时长)` 列表编译为事件序列；每段之间空出 `interval_ms`。"""
    events: list[Event] = []
    t = 0.0
    for key, hold_ms in items:
        events.append((t, Action("key_down", key)))
        events.append((t + hold_ms, Action("key_up", key)))
        t += hold_ms + interval_ms
    return events


def plan_key(key: str, hold_ms: float, repeat: int, interval_ms: float) -> list[Event]:
    """同一键重复 `repeat` 次。"""
    return plan_sequence([(key, hold_ms)] * repeat, interval_ms)


def plan_scale(keys: Sequence[str], hold_ms: float, interval_ms: float) -> list[Event]:
    """按键位顺序依次弹奏（默认即 1 2 3 4 5 6 7 1̇ 的上行音阶）。"""
    return plan_sequence([(k, hold_ms) for k in keys], interval_ms)


def plan_hold_sweep(key: str, durations_ms: Sequence[float], gap_ms: float) -> list[Event]:
    """用不同的按时长依次弹同一个键，用于判断游戏能接受的最短按时长。"""
    return plan_sequence([(key, d) for d in durations_ms], gap_ms)


def plan_modifier_compare(
    button: str,
    keys: Sequence[str] = INSTRUMENT_KEYS,
    *,
    lead_ms: float = 20.0,
    hold_ms: float = 350.0,
    tail_ms: float = 40.0,
    ref_gap_ms: float = 1000.0,
    key_gap_ms: float = 650.0,
    rounds: int = 2,
) -> list[Event]:
    """标定用计划：先弹「按住鼠标键 + z」的参考音，再逐个弹普通键，最后重复参考音。

    参考音是「按住修饰键时按 z」，候选是松开修饰键时的 8 个普通音。
    用户只需判断参考音与哪个候选音**听起来一样**，无需任何乐理知识。
    """
    events: list[Event] = []
    t = 0.0
    for _ in range(rounds):
        events.append((t, Action("mouse_down", button)))
        events.append((t + lead_ms, Action("key_down", "z")))
        events.append((t + lead_ms + hold_ms, Action("key_up", "z")))
        events.append((t + lead_ms + hold_ms + tail_ms, Action("mouse_up", button)))
        t += lead_ms + hold_ms + tail_ms + ref_gap_ms
        for key in keys:
            events.append((t, Action("key_down", key)))
            events.append((t + hold_ms, Action("key_up", key)))
            t += hold_ms + key_gap_ms
    return events


def plan_mouse(button: str, hold_ms: float, repeat: int, gap_ms: float) -> list[Event]:
    """只按/松鼠标键，用于确认游戏是否响应注入的鼠标事件。"""
    events: list[Event] = []
    t = 0.0
    for _ in range(repeat):
        events.append((t, Action("mouse_down", button)))
        events.append((t + hold_ms, Action("mouse_up", button)))
        t += hold_ms + gap_ms
    return events


# ── 注入执行 ──────────────────────────────────────────────────────────────────


def make_key_input(key: str, up: bool) -> INPUT:
    """构造一次键盘输入（扫描码方式，游戏通常只认这种）。"""
    try:
        scan = SCAN_CODES[key]
    except KeyError:
        raise KeyError(f"未登记的按键：{key!r}（可用：{' '.join(sorted(SCAN_CODES))}）") from None
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if up else 0)
    return INPUT(
        type=INPUT_KEYBOARD,
        ki=KEYBDINPUT(wVk=0, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=None),
    )


def make_mouse_input(button: str, up: bool) -> INPUT:
    """构造一次鼠标键输入（不移动指针）。"""
    try:
        down_flag, up_flag = BUTTON_FLAGS[button]
    except KeyError:
        raise KeyError(f"未知鼠标键：{button!r}（可用：left / middle / right）") from None
    return INPUT(
        type=INPUT_MOUSE,
        mi=MOUSEINPUT(0, 0, 0, up_flag if up else down_flag, 0, None),
    )


def send_action(action: Action) -> None:
    """把一次动作真正送进系统的 SendInput 队列。"""
    if action.kind.startswith("key"):
        item = make_key_input(action.name, up=action.kind == "key_up")
    else:
        item = make_mouse_input(action.name, up=action.kind == "mouse_up")
    sent = _user32.SendInput(1, ctypes.byref(item), ctypes.sizeof(item))
    if sent != 1:
        raise OSError(f"SendInput 失败：{action.kind} {action.name}（错误码 {ctypes.get_last_error()}）")


class InputSender:
    """执行动作并跟踪「按下未松开」的键，保证任何退出路径都能全部释放。"""

    def __init__(self, emit: Callable[[Action], None] | None = None) -> None:
        self._emit = emit if emit is not None else send_action
        self._pressed: set[Action] = set()

    @property
    def pressed(self) -> frozenset[Action]:
        return frozenset(self._pressed)

    def execute(self, action: Action) -> None:
        self._emit(action)
        if action.is_down:
            self._pressed.add(action)
        else:
            self._pressed.discard(Action(_opposite(action.kind), action.name))

    def release_all(self) -> None:
        """松开所有仍被按住的键/鼠标键。"""
        for action in sorted(self._pressed, key=lambda a: (a.name, a.kind)):
            self._emit(Action(_opposite(action.kind), action.name))
        self._pressed.clear()


def _opposite(kind: str) -> str:
    """down ↔ up 双向映射：key_down ↔ key_up、mouse_down ↔ mouse_up。"""
    if kind.endswith("_down"):
        return kind.replace("_down", "_up")
    return kind.replace("_up", "_down")


def sleep_until(deadline: float) -> None:
    """睡到指定时刻；最后 2ms 改为忙等，避免 sleep 粒度造成的抖动。"""
    while True:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            return
        if remaining > 0.002:
            time.sleep(remaining - 0.002)


def run_events(
    events: Sequence[Event],
    sender: InputSender,
    *,
    countdown_s: float,
    dry_run: bool,
    verbose: bool,
    log: Callable[[str], None] = print,
) -> None:
    """按计划执行事件；`dry_run` 时只打印不注入。"""
    ordered = sorted(events, key=lambda e: e[0])
    if dry_run:
        for t_ms, action in ordered:
            log(f"  {t_ms:9.1f} ms  {action.kind:<11} {action.name}")
        log(f"  （dry-run：共 {len(ordered)} 个事件，未发送任何输入）")
        return
    if countdown_s > 0:
        _countdown(countdown_s, log)
    start = time.perf_counter()
    for t_ms, action in ordered:
        sleep_until(start + t_ms / 1000.0)
        sender.execute(action)
        if verbose:
            log(f"  {t_ms:9.1f} ms  {action.kind:<11} {action.name}")


def _countdown(seconds: float, log: Callable[[str], None]) -> None:
    log(f"  {seconds:.0f} 秒后开始 —— 请立刻切回游戏窗口（保持游戏在前台）")
    deadline = time.perf_counter() + seconds
    shown = int(seconds) + 1
    while True:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            break
        whole = int(remaining) + 1
        if whole < shown:
            shown = whole
            log(f"  {whole} …")
        time.sleep(0.05)


# ── 环境自检 ──────────────────────────────────────────────────────────────────


def foreground_window() -> tuple[str, str]:
    """返回当前前台窗口的 (标题, 类名)。"""
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return "", ""
    buf = ctypes.create_unicode_buffer(256)
    _user32.GetWindowTextW(hwnd, buf, 256)
    cls = ctypes.create_unicode_buffer(256)
    _user32.GetClassNameW(hwnd, cls, 256)
    return buf.value, cls.value


def is_admin() -> bool:
    """当前进程是否以管理员身份运行（游戏若提权运行，非管理员进程的注入可能被系统拦截）。"""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


# ── 命令行 ────────────────────────────────────────────────────────────────────

RISK_NOTE = (
    "提示：本工具只发送口琴所需的按键与鼠标按键，不连发、不常驻、不读写游戏内存。\n"
    "      但游戏内使用自动输入存在被判定异常的风险，请自行评估，并只在安全场景（训练场/靶场）测试。"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="p0_sendinput_demo",
        description="纯 Python（SendInput）注入实验：验证游戏是否接受注入输入、测量按时长与标定半音数。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="常用：scale / hold-sweep / compare --button right",
    )
    parser.add_argument("--countdown", type=float, default=5.0, help="开始前的倒计时秒数（默认 5）")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要发送的事件，不真的注入")
    parser.add_argument("--verbose", action="store_true", help="实时打印每个事件（可能引入毫秒级抖动）")
    parser.add_argument("--yes", action="store_true", help="跳过开始前的确认提示")

    sub = parser.add_subparsers(dest="mode", required=True)

    sub.add_parser("check", help="环境自检：管理员权限、前台窗口")

    p_key = sub.add_parser("key", help="重复弹同一个键")
    p_key.add_argument("--key", default="z", help="要弹的键（默认 z）")
    p_key.add_argument("--hold-ms", type=float, default=80.0, help="每次按时长毫秒（默认 80）")
    p_key.add_argument("--repeat", type=int, default=5, help="重复次数（默认 5）")
    p_key.add_argument("--interval-ms", type=float, default=400.0, help="两次之间的间隔毫秒（默认 400）")

    p_scale = sub.add_parser("scale", help="依次弹 z x c v b n m ,（上行音阶）")
    p_scale.add_argument("--hold-ms", type=float, default=200.0, help="每次按时长毫秒（默认 200）")
    p_scale.add_argument("--interval-ms", type=float, default=250.0, help="音符间隔毫秒（默认 250）")
    p_scale.add_argument("--repeat", type=int, default=2, help="整条音阶重复次数（默认 2）")

    p_sweep = sub.add_parser("hold-sweep", help="不同按时长对比，测游戏能接受的最短按时长")
    p_sweep.add_argument("--key", default="z", help="要弹的键（默认 z）")
    p_sweep.add_argument("--durations", default="20,30,40,50,80,120", help="按时长列表（毫秒，逗号分隔）")
    p_sweep.add_argument("--gap-ms", type=float, default=1500.0, help="两段之间的间隔毫秒（默认 1500）")

    p_cmp = sub.add_parser("compare", help="标定：按住鼠标键时按 z，对比普通键，倒推半音数")
    p_cmp.add_argument("--button", required=True, choices=sorted(BUTTON_FLAGS), help="要标定的鼠标键")
    p_cmp.add_argument("--hold-ms", type=float, default=350.0, help="每个音按时长毫秒（默认 350）")
    p_cmp.add_argument("--rounds", type=int, default=2, help="整组重复次数（默认 2）")

    p_mouse = sub.add_parser("mouse", help="只按/松鼠标键（确认游戏是否响应注入的鼠标事件）")
    p_mouse.add_argument("--button", required=True, choices=sorted(BUTTON_FLAGS), help="要测的鼠标键")
    p_mouse.add_argument("--hold-ms", type=float, default=300.0, help="按住时长毫秒（默认 300）")
    p_mouse.add_argument("--repeat", type=int, default=3, help="重复次数（默认 3）")
    p_mouse.add_argument("--gap-ms", type=float, default=800.0, help="间隔毫秒（默认 800）")

    return parser


def _parse_durations(text: str) -> list[float]:
    try:
        values = [float(part) for part in text.split(",") if part.strip()]
    except ValueError:
        raise SystemExit(f"--durations 需要逗号分隔的数字，收到：{text!r}") from None
    if not values or any(v <= 0 for v in values):
        raise SystemExit("--durations 必须都是正数")
    return values


def _plan_for(args: argparse.Namespace) -> list[Event]:
    if args.mode == "key":
        return plan_key(args.key, args.hold_ms, args.repeat, args.interval_ms)
    if args.mode == "scale":
        return plan_scale(INSTRUMENT_KEYS, args.hold_ms, args.interval_ms) * args.repeat
    if args.mode == "hold-sweep":
        return plan_hold_sweep(args.key, _parse_durations(args.durations), args.gap_ms)
    if args.mode == "compare":
        return plan_modifier_compare(args.button, hold_ms=args.hold_ms, rounds=args.rounds)
    if args.mode == "mouse":
        return plan_mouse(args.button, args.hold_ms, args.repeat, args.gap_ms)
    raise SystemExit(f"未知模式：{args.mode}")


def _describe(args: argparse.Namespace) -> None:
    """播放前把「用户需要数着什么」打印清楚。"""
    if args.mode == "scale":
        print(f"  将依次弹：{' '.join(INSTRUMENT_KEYS)}" + (f"（重复 {args.repeat} 遍）" if args.repeat > 1 else ""))
        print("  这一步只验证「注入是否生效」，请确认游戏里能听到音（不是乱音/无声）。")
    elif args.mode == "hold-sweep":
        durations = _parse_durations(args.durations)
        print("  将依次用以下按时长弹同一个键，间隔 1.5 秒：")
        for i, d in enumerate(durations, 1):
            print(f"    第 {i} 段：{d:g} ms")
        print("  请记下「第几段开始能稳定听到声音」——那一段就是游戏能接受的最短按时长上限。")
    elif args.mode == "compare":
        label = {"left": "左键（口述=降调）", "middle": "滚轮中键（口述=半音）", "right": "右键（口述=升调）"}[
            args.button
        ]
        print(f"  标定目标：{label}")
        print(f"  每轮先弹「按住{label} + z」的参考音，然后逐个弹普通键：{' '.join(INSTRUMENT_KEYS)}")
        print("  你只需要回答：参考音跟第几个普通键**听起来一样**？")
    elif args.mode == "mouse":
        print(f"  将按/松鼠标键：{args.button}（共 {args.repeat} 次）")
        print("  ⚠ 若测左键，游戏里可能是开火；务必在训练场/靶场等安全场景进行。")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.mode == "check":
        title, cls = foreground_window()
        print(f"  Python      : {sys.version.split()[0]} ({sys.executable})")
        print(f"  管理员运行  : {'是' if is_admin() else '否'}")
        print(f"  前台窗口    : {title or '（无）'}  [class={cls or '-'}]")
        print("  说明：若游戏以管理员身份运行，非管理员的进程可能无法把输入送进游戏窗口（系统 UIPI 限制）。")
        print("        此时请用「以管理员身份运行」的终端重新执行本脚本。")
        return 0

    sender = InputSender()
    atexit.register(sender.release_all)
    events = _plan_for(args)

    print(RISK_NOTE)
    print(f"  模式：{args.mode}    事件数：{len(events)}" + ("    [dry-run]" if args.dry_run else ""))
    _describe(args)
    if not args.dry_run and not args.yes:
        input("  按 Enter 继续（之后请把游戏切到前台）…")

    try:
        run_events(
            events,
            sender,
            countdown_s=0.0 if args.dry_run else args.countdown,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
    except KeyboardInterrupt:
        print("\n  已中断。", file=sys.stderr)
        return 130
    finally:
        released = len(sender.pressed)
        sender.release_all()
        if released:
            print(f"  已释放 {released} 个仍按住的键。")

    print("  完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
