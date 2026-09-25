"""主窗口：曲谱库 + 编辑器/预览 + 播放控制 + 设置/校准（SPEC §7、§8）。"""

from __future__ import annotations

import ctypes
import dataclasses
from ctypes import wintypes
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from kouqin.core.compile import PlanError, compile_plan
from kouqin.core.instrument import load_instrument, reachable
from kouqin.core.score import ScoreError
from kouqin.hotkey.win32 import HotkeyManager
from kouqin.input.win32 import InputSender, is_elevated
from kouqin.player.engine import Player
from kouqin.scores.kq import parse_kq, render_kq
from kouqin.scores.library import count_unreachable, list_scores, load_score, save_score
from kouqin.settings import load_settings
from kouqin.ui.dialogs import CalibrationDialog, SettingsDialog
from kouqin.ui.preview import NotePreview


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt_x", wintypes.LONG),
        ("pt_y", wintypes.LONG),
    ]


class PlayerBridge(QtCore.QObject):
    """把播放线程的回调搬到 UI 线程（跨线程信号默认是队列投递）。"""

    progress = QtCore.Signal(int, int)
    state_changed = QtCore.Signal(str)


class NativeEventFilter(QtCore.QAbstractNativeEventFilter):
    """拦截 `WM_HOTKEY` 并交给热键管理器。"""

    def __init__(self, manager: HotkeyManager) -> None:
        super().__init__()
        self.manager = manager

    def nativeEventFilter(self, event_type, message):  # noqa: N802 (Qt 命名)
        try:
            if event_type in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
                msg = ctypes.cast(int(message), ctypes.POINTER(MSG)).contents
                if self.manager.handle_message(int(msg.message), int(msg.wParam)):
                    return True, 0
        except Exception:  # noqa: BLE001 —— 过滤失败不应影响界面
            pass
        return False, 0


class MainWindow(QtWidgets.QMainWindow):
    """应用主窗口。"""

    def __init__(self, *, config_dir: str | Path, scores_dir: str | Path) -> None:
        super().__init__()
        self.setWindowTitle("口琴自动演奏宏")
        self.resize(1180, 720)

        self.config_dir = Path(config_dir)
        self.scores_dir = Path(scores_dir)
        self.instrument_path = self.config_dir / "instrument.json"
        self.settings_path = self.config_dir / "settings.json"

        self.sender = InputSender()
        self.hotkey_manager = HotkeyManager()
        self.event_filter = NativeEventFilter(self.hotkey_manager)
        QtWidgets.QApplication.instance().installNativeEventFilter(self.event_filter)

        self.bridge = PlayerBridge()
        self.bridge.progress.connect(self._on_progress)
        self.bridge.state_changed.connect(self._on_state)

        self.player: Player | None = None
        self.score = None
        self.plan = None
        self._hotkeys_registered = False
        self._parse_timer = QtCore.QTimer(self)
        self._parse_timer.setSingleShot(True)
        self._parse_timer.setInterval(300)
        self._parse_timer.timeout.connect(self._reparse)

        self._build_menu()
        self._build_ui()
        self.refresh_library()
        self._load_default_score()

    # ── 界面搭建 ──

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("文件(&F)")
        file_menu.addAction("新建", self.new_score, QtGui.QKeySequence.StandardKey.New)
        file_menu.addAction("打开…", self.open_from_dialog, QtGui.QKeySequence.StandardKey.Open)
        file_menu.addAction("导入（.kq / .json / .mid）…", self.import_score)
        file_menu.addAction("导出为…", self.export_score, QtGui.QKeySequence.StandardKey.SaveAs)
        file_menu.addSeparator()
        file_menu.addAction("在资源管理器中打开曲谱库", self.reveal_scores_dir)
        file_menu.addSeparator()
        file_menu.addAction("退出", self.close, QtGui.QKeySequence.StandardKey.Quit)

        play_menu = self.menuBar().addMenu("播放(&P)")
        play_menu.addAction("开始 / 停止", self.toggle_play, "Ctrl+Alt+P")
        play_menu.addAction("暂停 / 继续", self.toggle_pause, "Ctrl+Alt+U")
        play_menu.addAction("急停（松开所有键）", self.panic, "Ctrl+Alt+K")

        setup_menu = self.menuBar().addMenu("设置(&S)")
        setup_menu.addAction("播放参数与键位…", self.open_settings)
        setup_menu.addAction("校准…", self.open_calibration)

        help_menu = self.menuBar().addMenu("帮助(&H)")
        help_menu.addAction("关于", self.show_about)

    def _build_ui(self) -> None:
        self.library = QtWidgets.QListWidget()
        self.library.setMinimumWidth(260)
        self.library.itemDoubleClicked.connect(lambda _item: self.open_selected())

        self.editor = QtWidgets.QPlainTextEdit()
        self.editor.setPlaceholderText("在这里写简谱，例如：\n1 1 5 5 | 6 6 5- |")
        self.editor.setFont(QtGui.QFont("Consolas", 11))
        self.editor.textChanged.connect(self._parse_timer.start)

        self.preview = NotePreview()
        self.issues_view = QtWidgets.QPlainTextEdit()
        self.issues_view.setReadOnly(True)
        self.issues_view.setMaximumHeight(90)
        self.issues_view.setPlaceholderText("解析与编译的问题会显示在这里")

        middle = QtWidgets.QWidget()
        middle_layout = QtWidgets.QVBoxLayout(middle)
        middle_layout.addWidget(self.editor, 3)
        middle_layout.addWidget(self.preview, 2)
        middle_layout.addWidget(self.issues_view, 1)

        splitter = QtWidgets.QSplitter()
        splitter.addWidget(self.library)
        splitter.addWidget(middle)
        splitter.setStretchFactor(1, 1)

        # 播放控制条
        self.play_button = QtWidgets.QPushButton("开始")
        self.pause_button = QtWidgets.QPushButton("暂停")
        self.stop_button = QtWidgets.QPushButton("停止")
        self.loop_check = QtWidgets.QCheckBox("循环")
        self.speed_spin = QtWidgets.QDoubleSpinBox()
        self.speed_spin.setRange(0.5, 2.0)
        self.speed_spin.setSingleStep(0.1)
        self.speed_spin.setValue(1.0)
        self.speed_spin.setPrefix("速度 ")
        self.transpose_spin = QtWidgets.QSpinBox()
        self.transpose_spin.setRange(-12, 12)
        self.transpose_spin.setPrefix("移调 ")
        self.transpose_spin.setSuffix(" 半音")
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setFormat("%v / %m")

        play_bar = QtWidgets.QHBoxLayout()
        for widget in (self.play_button, self.pause_button, self.stop_button, self.loop_check,
                       self.speed_spin, self.transpose_spin):
            play_bar.addWidget(widget)
        play_bar.addWidget(self.progress_bar, 1)

        self.play_button.clicked.connect(self.toggle_play)
        self.pause_button.clicked.connect(self.toggle_pause)
        self.stop_button.clicked.connect(self.stop_playback)
        self.speed_spin.valueChanged.connect(lambda _v: self._reparse())
        self.transpose_spin.valueChanged.connect(lambda _v: self._reparse())

        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.addWidget(splitter, 1)
        layout.addLayout(play_bar)
        self.setCentralWidget(central)

        self.status_label = QtWidgets.QLabel("就绪")
        self.statusBar().addWidget(self.status_label)
        self.statusBar().addPermanentWidget(QtWidgets.QLabel(f"曲谱库：{self.scores_dir}"))

    # ── 曲谱库与编辑器 ──

    @property
    def instrument(self):
        return load_instrument(self.instrument_path)

    @property
    def settings(self):
        return load_settings(self.settings_path)

    def refresh_library(self) -> None:
        self.library.clear()
        instrument = self.instrument
        settings = self.settings
        reference = (settings.midi["reference_note"], settings.midi["reference_semitone"])
        for entry in list_scores(self.scores_dir, instrument, reference):
            beats = entry.duration_beat
            seconds = beats * 60 / entry.tempo_bpm if entry.tempo_bpm else 0
            text = f"{entry.title}　{entry.note_count} 音　{seconds:.0f}s\n{entry.status_text}"
            item = QtWidgets.QListWidgetItem(text)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, str(entry.path))
            if entry.error:
                item.setForeground(QtGui.QColor("#f28b82"))
            elif entry.unreachable:
                item.setForeground(QtGui.QColor("#fdd663"))
            self.library.addItem(item)

    def _load_default_score(self) -> None:
        if self.library.count() == 0:
            self.new_score()
            return
        self.library.setCurrentRow(0)
        self.open_selected()

    def open_selected(self) -> None:
        item = self.library.currentItem()
        if item is None:
            return
        path = Path(item.data(QtCore.Qt.ItemDataRole.UserRole))
        try:
            score = load_score(path, self.instrument, (
                self.settings.midi["reference_note"], self.settings.midi["reference_semitone"]
            ))
        except (ScoreError, ValueError, OSError) as exc:
            self._show_issues([f"无法打开 {path.name}：{exc}"])
            return
        if path.suffix.lower() in {".mid", ".midi"}:
            # MIDI 不是文本，展示成等价简谱，便于查看与另存
            self.editor.setPlainText(render_kq(score))
        else:
            self.editor.setPlainText(path.read_text(encoding="utf-8"))
        self.status_label.setText(f"已打开：{path.name}")
        self._parse_now()

    def _parse_now(self) -> None:
        """显式操作（打开/新建/切换）后立即解析，不等防抖定时器。"""
        self._parse_timer.stop()
        self._reparse()

    def new_score(self) -> None:
        self.editor.setPlainText("@title 新曲谱\n@tempo 100\n@meter 4/4\n\n1 2 3 4 | 5 6 7 1' |\n")
        self.status_label.setText("新建曲谱")
        self._parse_now()

    def open_from_dialog(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "打开曲谱", str(self.scores_dir), "曲谱 (*.kq *.json *.mid *.midi)"
        )
        if path:
            self.editor.setPlainText(Path(path).read_text(encoding="utf-8", errors="replace"))
            self.status_label.setText(f"已打开：{Path(path).name}")
            self._parse_now()

    def import_score(self) -> None:
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "导入曲谱", str(self.scores_dir), "曲谱 (*.kq *.json *.mid *.midi)"
        )
        for path in paths:
            source = Path(path)
            target = self.scores_dir / source.name
            try:
                score = load_score(source, self.instrument, (
                    self.settings.midi["reference_note"], self.settings.midi["reference_semitone"]
                ))
                save_score(score, target.with_suffix(".kq"))
            except (ScoreError, ValueError, OSError) as exc:
                self._show_issues([f"导入 {source.name} 失败：{exc}"])
        self.refresh_library()

    def export_score(self) -> None:
        score = self.score
        if score is None:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "导出曲谱", str(self.scores_dir / f"{score.title}.kq"), "简谱 (*.kq);;JSON (*.kq.json)"
        )
        if path:
            target = Path(path)
            save_score(score, target.with_suffix(".json") if target.suffix == ".json" else target)
            self.refresh_library()

    def reveal_scores_dir(self) -> None:
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self.scores_dir)))

    # ── 解析与预览 ──

    def _reparse(self) -> None:
        text = self.editor.toPlainText()
        messages: list[str] = []
        score = None
        try:
            score = parse_kq(text)
        except ScoreError as exc:
            messages.extend(f"[{issue.code}] 第 {issue.line or '?'} 行 {issue.message}" for issue in exc.issues)

        self.score = score
        self.plan = None
        if score is None:
            self.preview.set_score(None)
            self._show_issues(messages)
            self.play_button.setEnabled(False)
            return

        messages.extend(f"[{issue.code}] {issue.message}" for issue in score.issues)
        instrument = self.instrument
        if not instrument.verified:
            messages.append("[CP004] 乐器配置未校准：请先在「设置 → 校准」里核对按键语义")
            self.play_button.setEnabled(False)
        else:
            self.play_button.setEnabled(True)

        adjusted = dataclasses.replace(score, transpose=score.transpose + self.transpose_spin.value())
        unreachable = {
            note.pitch + adjusted.transpose
            for note in score.notes
            if note.pitch is not None
        } - reachable(instrument)
        if unreachable:
            messages.append(f"[CP001] 有 {count_unreachable(adjusted, instrument)} 个音超出乐器音域（已在预览中标红）")
        self.preview.set_score(adjusted, unreachable)

        try:
            self.plan = compile_plan(adjusted, instrument, self.settings, speed=self.speed_spin.value())
            messages.extend(f"[{issue.code}] {issue.message}" for issue in self.plan.issues)
            if unreachable:
                self.play_button.setEnabled(False)
        except PlanError as exc:
            messages.extend(f"[{issue.code}] {issue.message}" for issue in exc.issues)
            self.play_button.setEnabled(False)

        if self.plan is not None:
            self.progress_bar.setRange(0, max(len(self.plan.notes), 1))
            self.progress_bar.setValue(0)
            self.status_label.setText(
                f"{score.title}　{len(self.plan.notes)} 音　{self.plan.duration_ms / 1000:.1f} 秒"
            )
        self._show_issues(messages)

    def _show_issues(self, messages: list[str]) -> None:
        self.issues_view.setPlainText("\n".join(messages))

    # ── 播放控制 ──

    def toggle_play(self) -> None:
        if self.player is not None and self.player.state in {"countdown", "playing", "paused"}:
            self.stop_playback()
            return
        self.start_playback()

    def start_playback(self) -> None:
        if self.plan is None:
            QtWidgets.QMessageBox.information(self, "无法播放", "请先修正曲谱或完成校准。")
            return
        if not is_elevated():
            self.statusBar().showMessage("提示：若游戏以管理员运行，本程序也需以管理员运行才能注入", 8000)

        settings = self.settings
        self.player = Player(
            self.plan,
            sender=self.sender,
            loop=self.loop_check.isChecked(),
            countdown_ms=settings.playback["countdown_ms"],
            on_progress=lambda index, total: self.bridge.progress.emit(index, total),
            on_state=lambda state: self.bridge.state_changed.emit(state),
        )
        self.player.play()
        self._set_playing_ui(True)

    def toggle_pause(self) -> None:
        if self.player is None:
            return
        if self.player.state == "paused":
            self.player.resume()
        elif self.player.state == "playing":
            self.player.pause()

    def stop_playback(self) -> None:
        if self.player is not None:
            self.player.stop()
        self._set_playing_ui(False)

    def panic(self) -> None:
        if self.player is not None:
            self.player.panic()
        self.sender.release_all()
        self._set_playing_ui(False)
        self.statusBar().showMessage("已急停：所有按键已释放", 5000)

    def _set_playing_ui(self, playing: bool) -> None:
        self.play_button.setText("停止" if playing else "开始")
        self.pause_button.setEnabled(playing)
        self.stop_button.setEnabled(playing)
        self.editor.setReadOnly(playing)

    def _on_state(self, state: str) -> None:
        labels = {
            "idle": "空闲",
            "countdown": "倒计时中（切回游戏）",
            "playing": "播放中",
            "paused": "已暂停",
            "stopped": "已完成",
            "error": "注入失败",
        }
        self.status_label.setText(labels.get(state, state))
        if state in {"idle", "stopped", "error"}:
            self._set_playing_ui(False)
            if state == "error" and self.player is not None and self.player.last_error:
                QtWidgets.QMessageBox.warning(self, "注入失败", self.player.last_error)

    def _on_progress(self, index: int, total: int) -> None:
        self.progress_bar.setRange(0, max(total, 1))
        self.progress_bar.setValue(index + 1)
        self.preview.set_current_note(index)

    # ── 设置与校准 ──

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.instrument_path, self.settings_path, self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self.refresh_library()
            self._reparse()

    def open_calibration(self) -> None:
        dialog = CalibrationDialog(self.instrument_path, self.sender, self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self.refresh_library()
            self._reparse()

    def show_about(self) -> None:
        QtWidgets.QMessageBox.information(
            self,
            "关于",
            "口琴自动演奏宏 v1\n\n"
            "按乐谱在《三角洲行动》里自动演奏口琴道具。\n"
            "只发送按键与鼠标键，不读写游戏内存、不修改游戏文件。\n\n"
            "快捷键：Ctrl+Alt+P 开始/停止　Ctrl+Alt+U 暂停/继续　Ctrl+Alt+K 急停\n"
            "（可在「设置 → 全局热键」里改；每个热键旁有「检测」按钮验证是否被占用）\n"
            "许可：个人非商业（见 LICENSE）",
        )

    # ── 生命周期 ──

    def showEvent(self, event: QtGui.QShowEvent) -> None:  # noqa: N802 (Qt 命名)
        super().showEvent(event)
        if not self._hotkeys_registered:
            self._hotkeys_registered = True
            self._register_hotkeys()

    def _register_hotkeys(self) -> None:
        hwnd = int(self.winId())
        actions = {
            "toggle_play": self.toggle_play,
            "pause_resume": self.toggle_pause,
            "panic_release": self.panic,
        }
        failed = []
        self._hotkey_failures: list[str] = []
        for key, callback in actions.items():
            combo = self.settings.hotkeys.get(key, "")
            if not combo or not self.hotkey_manager.register(hwnd, combo, callback):
                failed.append(f"{key}（{combo}）")
        if failed:
            self._hotkey_failures = failed
            message = (
                f"全局热键注册失败：{'、'.join(failed)}\n"
                "多半是被别的程序（QQ、微信、录屏等）占用了。\n"
                "请到「设置 → 全局热键」点「检测」换一个可用的键，重启程序生效。"
            )
            self.statusBar().showMessage(f"热键未生效：{'、'.join(failed)}（可在设置里更换）", 20000)
            QtCore.QTimer.singleShot(0, lambda: QtWidgets.QMessageBox.warning(self, "全局热键未生效", message))

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802 (Qt 命名)
        if self.player is not None:
            self.player.shutdown()
        self.sender.release_all()
        self.hotkey_manager.unregister_all()
        QtWidgets.QApplication.instance().removeNativeEventFilter(self.event_filter)
        super().closeEvent(event)
