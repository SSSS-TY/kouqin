"""设置与校准对话框（SPEC §8）。"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6 import QtWidgets

from kouqin.core.instrument import load_instrument
from kouqin.settings import DEFAULT_HOTKEYS, DEFAULT_PLAYBACK, load_settings, save_settings


def _spin(value: int, minimum: int = 0, maximum: int = 60000, suffix: str = " ms") -> QtWidgets.QSpinBox:
    box = QtWidgets.QSpinBox()
    box.setRange(minimum, maximum)
    box.setValue(int(value))
    box.setSuffix(suffix)
    return box


class SettingsDialog(QtWidgets.QDialog):
    """播放参数、全局热键、键位表。保存后写回 config/ 下的两个 JSON。"""

    def __init__(self, instrument_path: str | Path, settings_path: str | Path, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.instrument_path = Path(instrument_path)
        self.settings_path = Path(settings_path)
        self.settings = load_settings(self.settings_path)
        self.instrument_data = json.loads(self.instrument_path.read_text(encoding="utf-8"))

        tabs = QtWidgets.QTabWidget()
        tabs.addTab(self._build_playback_tab(), "播放参数")
        tabs.addTab(self._build_hotkey_tab(), "全局热键")
        tabs.addTab(self._build_keys_tab(), "键位表")

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Save | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

    def _build_playback_tab(self) -> QtWidgets.QWidget:
        playback = self.settings.playback
        self.min_hold = _spin(playback["min_hold_ms"])
        self.note_gap = _spin(playback["note_gap_ms"])
        self.mod_lead = _spin(playback["modifier_lead_ms"])
        self.mod_tail = _spin(playback["modifier_tail_ms"])
        self.countdown = _spin(playback["countdown_ms"], maximum=60000)
        self.retrigger = QtWidgets.QCheckBox("长音超过上限时分段重触发")
        self.retrigger.setChecked(bool(playback["retrigger_long_notes"]))
        self.sustain_enabled = QtWidgets.QCheckBox("已实测长音上限")
        self.sustain = _spin(playback["sustain_limit_ms"] or 8000, minimum=200, maximum=60000)
        if playback["sustain_limit_ms"] is None:
            self.sustain_enabled.setChecked(False)
            self.sustain.setEnabled(False)
        else:
            self.sustain_enabled.setChecked(True)
        self.sustain_enabled.toggled.connect(self.sustain.setEnabled)

        form = QtWidgets.QFormLayout()
        form.addRow("最短按时长", self.min_hold)
        form.addRow("音符间隔", self.note_gap)
        form.addRow("修饰键提前量", self.mod_lead)
        form.addRow("修饰键尾延迟", self.mod_tail)
        form.addRow("开始前倒计时", self.countdown)
        form.addRow(self.retrigger)
        form.addRow(self.sustain_enabled, self.sustain)
        hint = QtWidgets.QLabel(
            "长音上限未实测时保持关闭——此时编译器如实按住整个时值，不做切分。\n"
            "用 `python tools\\p0_sendinput_demo.py sustain` 测得数值后再填入。"
        )
        hint.setWordWrap(True)
        box = QtWidgets.QGroupBox("播放参数")
        inner = QtWidgets.QVBoxLayout(box)
        inner.addLayout(form)
        inner.addWidget(hint)
        return box

    def _build_hotkey_tab(self) -> QtWidgets.QWidget:
        self.hotkey_edits: dict[str, QtWidgets.QLineEdit] = {}
        labels = {
            "toggle_play": "开始 / 停止",
            "pause_resume": "暂停 / 继续",
            "panic_release": "急停（松开所有键）",
        }
        form = QtWidgets.QFormLayout()
        for key, label in labels.items():
            edit = QtWidgets.QLineEdit(self.settings.hotkeys.get(key, DEFAULT_HOTKEYS[key]))
            self.hotkey_edits[key] = edit
            form.addRow(label, edit)
        hint = QtWidgets.QLabel("形如 Ctrl+Alt+P。组合键会被系统吞掉，不会传给游戏。改完需重启程序生效。")
        hint.setWordWrap(True)
        box = QtWidgets.QGroupBox("全局热键")
        inner = QtWidgets.QVBoxLayout(box)
        inner.addLayout(form)
        inner.addWidget(hint)
        return box

    def _build_keys_tab(self) -> QtWidgets.QWidget:
        self.keys_table = QtWidgets.QTableWidget(len(self.instrument_data["keys"]), 3)
        self.keys_table.setHorizontalHeaderLabels(["按键", "音级", "八度"])
        for row, item in enumerate(self.instrument_data["keys"]):
            self.keys_table.setItem(row, 0, QtWidgets.QTableWidgetItem(item["key"]))
            self.keys_table.setItem(row, 1, QtWidgets.QTableWidgetItem(str(item["degree"])))
            self.keys_table.setItem(row, 2, QtWidgets.QTableWidgetItem(str(item["octave"])))
        self.keys_table.horizontalHeader().setStretchLastSection(True)
        hint = QtWidgets.QLabel("修改键位后请到「校准」页重新试拍确认。音级 1–7 对应大调音阶，八度 0 为中音区。")
        hint.setWordWrap(True)
        box = QtWidgets.QWidget()
        inner = QtWidgets.QVBoxLayout(box)
        inner.addWidget(self.keys_table)
        inner.addWidget(hint)
        return box

    def _save(self) -> None:
        playback = {
            "min_hold_ms": self.min_hold.value(),
            "note_gap_ms": self.note_gap.value(),
            "modifier_lead_ms": self.mod_lead.value(),
            "modifier_tail_ms": self.mod_tail.value(),
            "countdown_ms": self.countdown.value(),
            "retrigger_long_notes": self.retrigger.isChecked(),
            "sustain_limit_ms": self.sustain.value() if self.sustain_enabled.isChecked() else None,
        }
        settings = self.settings.__class__(
            playback=playback,
            hotkeys={key: edit.text().strip() for key, edit in self.hotkey_edits.items()},
            midi=dict(self.settings.midi),
        )
        save_settings(settings, self.settings_path)

        keys = []
        for row in range(self.keys_table.rowCount()):
            key_item = self.keys_table.item(row, 0)
            degree_item = self.keys_table.item(row, 1)
            octave_item = self.keys_table.item(row, 2)
            if key_item is None or not key_item.text().strip():
                continue
            try:
                keys.append(
                    {
                        "key": key_item.text().strip(),
                        "degree": int(degree_item.text()),
                        "octave": int(octave_item.text()),
                    }
                )
            except (AttributeError, ValueError):
                QtWidgets.QMessageBox.warning(self, "键位表", f"第 {row + 1} 行的音级/八度不是整数，已跳过")
        self.instrument_data["keys"] = keys
        self.instrument_path.write_text(
            json.dumps(self.instrument_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        self.accept()


class CalibrationDialog(QtWidgets.QDialog):
    """校准：试拍每种修饰组合，按游戏内显示的简谱回填半音数。"""

    def __init__(self, instrument_path: str | Path, sender, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("校准")
        self.instrument_path = Path(instrument_path)
        self.sender = sender
        self.instrument_data = json.loads(self.instrument_path.read_text(encoding="utf-8"))

        self.modifier_spins: dict[str, QtWidgets.QSpinBox] = {}
        form = QtWidgets.QFormLayout()
        for item in self.instrument_data["modifiers"]:
            spin = QtWidgets.QSpinBox()
            spin.setRange(-24, 24)
            spin.setValue(int(item["semitone"]))
            spin.setSuffix(" 半音")
            self.modifier_spins[item["button"]] = spin
            form.addRow(f"{item['label']}（{item['button']}）", spin)

        self.sets_table = QtWidgets.QTableWidget(len(self.instrument_data["modifier_sets"]), 3)
        self.sets_table.setHorizontalHeaderLabels(["修饰组合", "偏移", "试拍"])
        for row, entry in enumerate(self.instrument_data["modifier_sets"]):
            buttons = entry["buttons"]
            text = "＋".join(buttons) if buttons else "（不按鼠标）"
            self.sets_table.setItem(row, 0, QtWidgets.QTableWidgetItem(text))
            self.sets_table.setItem(row, 1, QtWidgets.QTableWidgetItem("—"))
            button = QtWidgets.QPushButton("试拍 z")
            button.clicked.connect(lambda _=False, b=tuple(buttons): self.try_note(b))
            self.sets_table.setCellWidget(row, 2, button)
        self.sets_table.resizeColumnsToContents()

        verify = QtWidgets.QCheckBox("我已在游戏内核对过上述音高，标记为「已校准」")
        verify.setChecked(bool(self.instrument_data.get("verified")))
        self.verify = verify

        hint = QtWidgets.QLabel(
            "做法：点「试拍 z」，看游戏里显示的简谱。\n"
            "· 按住左键 → 低音八度（−12）　· 按住中键 → 全部加 #（+1）　· 按住右键 → 高音八度（+12）\n"
            "· 两个键可叠加（左+中 = −11、右+中 = +13）\n"
            "若某项不符，把实测的半音数填到上面再试拍。\n\n"
            "⚠ 试拍会把按键发到**当前前台窗口**：请在游戏内（训练场）使用，或先确认前台窗口不会受影响。"
        )
        hint.setWordWrap(True)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Save | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addLayout(form)
        layout.addWidget(self.sets_table)
        layout.addWidget(verify)
        layout.addWidget(buttons)

    def try_note(self, buttons: tuple[str, ...], key: str = "z", hold_ms: int = 400) -> None:
        """真实注入一次「按住这些鼠标键 + 按 z」，用于对照游戏内标注。"""
        from kouqin.input.win32 import Action

        try:
            for button in buttons:
                self.sender.send(Action("mouse_down", button))
            self.sender.send(Action("key_down", key))
            QtWidgets.QApplication.processEvents()
        finally:
            self.sender.send(Action("key_up", key))
            for button in buttons:
                self.sender.send(Action("mouse_up", button))

    def _save(self) -> None:
        for item in self.instrument_data["modifiers"]:
            item["semitone"] = self.modifier_spins[item["button"]].value()
        self.instrument_data["verified"] = self.verify.isChecked()
        self.instrument_path.write_text(
            json.dumps(self.instrument_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        self.accept()
