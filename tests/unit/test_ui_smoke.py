"""界面冒烟测试（SPEC §8）：能构造主窗口、能加载曲谱、未校准时禁止播放。

不测交互细节（点击/拖拽）；无头环境用 Qt 的 offscreen 后端。
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6 import QtWidgets  # noqa: E402

from kouqin.ui.main_window import MainWindow  # noqa: E402

from tests.helpers import CONFIG_DIR, REPO_ROOT  # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def make_window(qt_app, tmp_path: Path, *, verified: bool = True) -> MainWindow:
    config = tmp_path / "config"
    config.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CONFIG_DIR / "instrument.json", config / "instrument.json")
    shutil.copy2(CONFIG_DIR / "settings.json", config / "settings.json")
    if not verified:
        data = json.loads((config / "instrument.json").read_text(encoding="utf-8"))
        data["verified"] = False
        (config / "instrument.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    scores = tmp_path / "scores"
    scores.mkdir(exist_ok=True)
    shutil.copy2(REPO_ROOT / "scores" / "twinkle.kq", scores / "twinkle.kq")
    return MainWindow(config_dir=config, scores_dir=scores)


def test_main_window_loads_first_score_and_compiles(qt_app, tmp_path: Path) -> None:
    window = make_window(qt_app, tmp_path)
    try:
        assert window.library.count() == 1
        assert window.score is not None
        assert window.plan is not None
        assert window.plan.title == "小星星"
        assert window.play_button.isEnabled()
    finally:
        window.close()


def test_unverified_instrument_disables_play(qt_app, tmp_path: Path) -> None:
    window = make_window(qt_app, tmp_path, verified=False)
    try:
        assert not window.play_button.isEnabled()
        assert "CP004" in window.issues_view.toPlainText()
    finally:
        window.close()


def test_broken_score_disables_play_and_reports(qt_app, tmp_path: Path) -> None:
    window = make_window(qt_app, tmp_path)
    try:
        window.editor.setPlainText("@title 坏谱\n\n1 9 3 4\n")
        window._reparse()
        assert not window.play_button.isEnabled()
        assert "KQ004" in window.issues_view.toPlainText()
    finally:
        window.close()

