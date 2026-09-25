"""`python -m kouqin` 入口。

图形界面（M4）尚未实现；当前提供命令行模式。给定子命令时走 `kouqin.cli`，
不带参数时打印用法提示。
"""

from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) > 1:
        from kouqin.cli import main as cli_main

        return cli_main()
    print(
        "口琴自动演奏宏（图形界面将在 M4 提供）\n\n"
        "当前可用：\n"
        "  python -m kouqin dry-run scores/twinkle.kq   # 打印事件序列（不注入）\n"
        "  python -m kouqin play    scores/twinkle.kq   # 倒计时后真实演奏\n"
        "  python -m kouqin check                       # 环境自检\n",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

