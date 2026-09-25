"""命令行入口：在图形界面（M4）完成之前，用它做 dry-run 与游戏内实测。

用法::

    python -m kouqin dry-run scores/twinkle.kq        # 只打印事件序列，不注入
    python -m kouqin play    scores/twinkle.kq        # 倒计时后真实演奏（训练场！）
    python -m kouqin check                            # 环境自检（是否管理员、能否注入）

支持 `.kq` / `.kq.json` / `.mid` 三种曲谱来源。
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
import time
from pathlib import Path
from typing import Sequence

from kouqin.core.compile import PlanError, compile_plan
from kouqin.core.instrument import load_instrument
from kouqin.core.score import ScoreError
from kouqin.scores.json_score import load_score_json
from kouqin.scores.kq import parse_kq_file
from kouqin.scores.midi import import_midi
from kouqin.settings import load_settings

DEFAULT_INSTRUMENT = "config/instrument.json"
DEFAULT_SETTINGS = "config/settings.json"


def load_score(path: Path, settings):
    """按扩展名选择解析器。"""
    suffix = path.suffix.lower()
    if suffix in {".mid", ".midi"}:
        return import_midi(
            path,
            settings.midi["reference_note"],
            settings.midi["reference_semitone"],
        ).score
    if suffix == ".json":
        return load_score_json(path)
    if suffix == ".kq":
        return parse_kq_file(path)
    raise ScoreError([]) if False else ValueError(f"不支持的曲谱格式：{path.name}（支持 .kq / .kq.json / .mid）")


def build_plan(args) -> tuple:
    instrument = load_instrument(args.instrument)
    settings = load_settings(args.settings)
    score = load_score(Path(args.score), settings)
    if args.transpose is not None:
        score = dataclasses.replace(score, transpose=args.transpose)
    plan = compile_plan(score, instrument, settings, speed=args.speed)
    return score, plan, instrument, settings


def print_issues(plan) -> None:
    for issue in plan.issues:
        level = {"error": "错误", "warning": "警告", "info": "提示"}.get(issue.level, issue.level)
        line = f"（第 {issue.line} 行）" if issue.line else ""
        print(f"  [{level}] {issue.code}{line} {issue.message}")


def cmd_dry_run(args) -> int:
    score, plan, instrument, _ = build_plan(args)
    print(f"曲谱：{score.title}　tempo={plan.tempo_bpm:g}　speed={plan.speed:g}　移调={plan.transpose:+d}")
    print(f"可演奏音：{len(plan.notes)}　事件：{len(plan.events)}　总长：{plan.duration_ms / 1000:.2f} 秒")
    print(f"初始平移：{plan.offset_ms} ms")
    print_issues(plan)
    print("\n  时刻(ms)   动作          目标")
    for event in plan.events[: args.limit]:
        print(f"  {event.t_ms:>8}  {event.op:<12}  {event.arg}")
    if len(plan.events) > args.limit:
        print(f"  …（其余 {len(plan.events) - args.limit} 个事件已省略，用 --limit 调整）")
    return 0


def cmd_play(args) -> int:
    from kouqin.input.win32 import InputSender, is_elevated
    from kouqin.player.engine import Player

    score, plan, _, settings = build_plan(args)
    print(f"曲谱：{score.title}　{len(plan.notes)} 个音　{plan.duration_ms / 1000:.2f} 秒")
    print_issues(plan)
    print("提示：本工具只发送口琴所需的按键与鼠标键，不连发、不常驻；请在训练场等安全场景使用。")
    countdown = args.countdown if args.countdown is not None else settings.playback["countdown_ms"] / 1000.0
    print(f"{countdown:.0f} 秒后开始 —— 请立刻切回游戏窗口" + ("（当前未以管理员运行，若游戏是管理员需同样提权）" if not is_elevated() else ""))

    sender = InputSender()
    player = Player(
        plan,
        sender=sender,
        countdown_ms=int(countdown * 1000),
        on_state=lambda state: print(f"  [状态] {state}"),
        on_progress=lambda index, total: print(f"  [进度] {index + 1}/{total}", end="\r"),
    )
    player.play()
    try:
        while player.state not in {"idle", "stopped", "error"}:
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\n  已中断，正在释放按键…", file=sys.stderr)
    finally:
        player.shutdown()
    print()
    if player.last_error:
        print(f"  注入失败：{player.last_error}", file=sys.stderr)
        return 3
    return 0


def cmd_check(_args) -> int:
    from kouqin.input.win32 import is_elevated, is_injectable

    print(f"  Python      : {sys.version.split()[0]} ({sys.executable})")
    print(f"  管理员运行  : {'是' if is_elevated() else '否'}")
    print(f"  可注入前台  : {'是' if is_injectable() else '否（前台窗口属更高权限进程，请以管理员运行本程序）'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m kouqin", description="口琴自动演奏宏（命令行）")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, help_text in (("dry-run", "只编译并打印事件序列（不注入）"), ("play", "倒计时后真实演奏")):
        item = sub.add_parser(name, help=help_text)
        item.add_argument("score", help="曲谱文件（.kq / .kq.json / .mid）")
        item.add_argument("--transpose", type=int, default=None, help="覆盖曲谱里的整体移调（半音）")
        item.add_argument("--speed", type=float, default=1.0, help="播放速度倍率（默认 1.0）")
        item.add_argument("--instrument", default=DEFAULT_INSTRUMENT, help="乐器配置路径")
        item.add_argument("--settings", default=DEFAULT_SETTINGS, help="播放设置路径")
        if name == "dry-run":
            item.add_argument("--limit", type=int, default=40, help="最多打印多少个事件（默认 40）")
        else:
            item.add_argument("--countdown", type=float, default=None, help="倒计时秒数（默认取设置里的值）")

    sub.add_parser("check", help="环境自检")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "dry-run":
            return cmd_dry_run(args)
        if args.command == "play":
            return cmd_play(args)
        return cmd_check(args)
    except (ScoreError, PlanError) as exc:
        print("无法继续：", file=sys.stderr)
        for issue in exc.issues:
            print(f"  [{issue.code}] {issue.message}", file=sys.stderr)
        return 2
    except (FileNotFoundError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

