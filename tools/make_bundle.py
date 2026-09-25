"""把「拷到另一台机器」所需的最小文件集打包到一个目录（可再压成 zip）。

用法::

    python tools/make_bundle.py                    # 输出到 %TEMP%\\kouqin_bundle
    python tools/make_bundle.py --dest D:\\usb\\kouqin   # 指定目录（如 U 盘）
    python tools/make_bundle.py --zip              # 额外生成同名 .zip，便于网盘/U 盘传输

拷贝清单的权威说明见 `docs/RUN_ON_B.md`；本脚本的清单与其保持一致。
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import Sequence

# (源文件相对路径, 打包后相对路径)
BUNDLE_FILES: tuple[tuple[str, str], ...] = (
    ("tools/p0_sendinput_demo.py", "tools/p0_sendinput_demo.py"),
    ("tests/unit/test_p0_sendinput_demo.py", "tests/unit/test_p0_sendinput_demo.py"),
    ("pytest.ini", "pytest.ini"),
    ("docs/RUN_ON_B.md", "README.txt"),
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DEST = Path(os.environ.get("TEMP", ".")) / "kouqin_bundle"


def default_dest() -> Path:
    """默认输出目录（%TEMP%\\kouqin_bundle）。"""
    return DEFAULT_DEST


def build_bundle(dest: Path, root: Path | None = None) -> list[Path]:
    """把清单里的文件复制到 `dest`，返回实际写出的文件列表。已存在的同名文件会被覆盖。"""
    root = REPO_ROOT if root is None else root
    written: list[Path] = []
    for source_rel, target_rel in BUNDLE_FILES:
        source = root / source_rel
        if not source.is_file():
            raise FileNotFoundError(f"清单里的源文件不存在：{source}")
        target = dest / target_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        written.append(target)
    return written


def make_zip(dest: Path) -> Path:
    """把 `dest` 目录压成同路径的 .zip（已存在则覆盖）。"""
    return Path(shutil.make_archive(str(dest), "zip", root_dir=str(dest)))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="打包「拷到 B 机」所需文件（清单见 docs/RUN_ON_B.md）")
    parser.add_argument("--dest", type=Path, default=default_dest(), help="输出目录（默认 %%TEMP%%\\kouqin_bundle）")
    parser.add_argument("--zip", action="store_true", help="额外生成同名 .zip")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    dest: Path = args.dest

    try:
        written = build_bundle(dest)
    except FileNotFoundError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    total = 0
    print(f"已打包到：{dest}")
    for path in written:
        size = path.stat().st_size
        total += size
        print(f"  {path.relative_to(dest)!s:<42} {size:>7,} B")
    print(f"  共 {len(written)} 个文件，{total / 1024:.1f} KB")

    if args.zip:
        archive = make_zip(dest)
        print(f"已生成压缩包：{archive}（{archive.stat().st_size / 1024:.1f} KB）")

    print("\n拷到 B 机后按 README.txt 操作；B 机只需 Python 3.9+，无需 pip 安装任何包。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
