"""打包脚本的离线测试：清单里的源文件必须真实存在，且能按预期结构产出。"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools import make_bundle
from tools.make_bundle import BUNDLE_FILES, REPO_ROOT, build_bundle, main


def test_every_manifest_source_exists_in_repo() -> None:
    missing = [src for src, _ in BUNDLE_FILES if not (REPO_ROOT / src).is_file()]
    assert missing == []


def test_bundle_contains_demo_and_readme(tmp_path: Path) -> None:
    written = build_bundle(tmp_path)
    rel = sorted(str(p.relative_to(tmp_path)).replace("\\", "/") for p in written)

    assert rel == [
        "README.txt",
        "pytest.ini",
        "tests/unit/test_p0_sendinput_demo.py",
        "tools/p0_sendinput_demo.py",
    ]
    # README 必须是 RUN_ON_B 的副本，工具必须是可独立运行的脚本
    assert (tmp_path / "README.txt").read_text(encoding="utf-8") == (
        REPO_ROOT / "docs/RUN_ON_B.md"
    ).read_text(encoding="utf-8")
    assert "SendInput" in (tmp_path / "tools/p0_sendinput_demo.py").read_text(encoding="utf-8")


def test_bundle_overwrites_existing_file(tmp_path: Path) -> None:
    stale = tmp_path / "tools/p0_sendinput_demo.py"
    stale.parent.mkdir(parents=True)
    stale.write_text("stale", encoding="utf-8")

    build_bundle(tmp_path)

    assert "stale" not in stale.read_text(encoding="utf-8")


def test_main_reports_file_count(tmp_path: Path, capsys) -> None:
    exit_code = main(["--dest", str(tmp_path / "bundle")])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "共 4 个文件" in out
    assert (tmp_path / "bundle/README.txt").is_file()


def test_build_bundle_rejects_missing_source(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        build_bundle(tmp_path / "out", root=tmp_path / "empty-repo")


def test_main_reports_missing_source_clearly(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setattr(make_bundle, "BUNDLE_FILES", (("does/not/exist.py", "x.py"),))

    exit_code = make_bundle.main(["--dest", str(tmp_path / "out")])

    assert exit_code == 1
    assert "不存在" in capsys.readouterr().err
