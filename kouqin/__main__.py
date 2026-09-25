"""`python -m kouqin` 入口。

不带参数 → 启动图形界面；带子命令 → 走命令行（`kouqin.cli`）。
"""

from __future__ import annotations

import sys
from pathlib import Path

USAGE = (
    "口琴自动演奏宏\n\n"
    "  python -m kouqin                              # 启动图形界面\n"
    "  python -m kouqin dry-run scores/twinkle.kq    # 打印事件序列（不注入）\n"
    "  python -m kouqin play    scores/twinkle.kq    # 倒计时后真实演奏\n"
    "  python -m kouqin check                        # 环境自检\n"
)


def run_gui() -> int:
    """启动 PySide6 界面（需要 PySide6）。"""
    try:
        from PySide6 import QtWidgets
    except ImportError:
        print("未安装 PySide6，无法启动图形界面。\n\n" + USAGE, file=sys.stderr)
        return 1

    from kouqin.ui.main_window import MainWindow

    root = Path(__file__).resolve().parent.parent
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow(config_dir=root / "config", scores_dir=root / "scores")
    window.show()
    return app.exec()


def main() -> int:
    if len(sys.argv) > 1:
        from kouqin.cli import main as cli_main

        return cli_main()
    return run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
