"""曲谱预览控件：横轴拍数、纵轴音高；不可达的音高标红（SPEC §8）。"""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

MIN_SEMITONE = -12
MAX_SEMITONE = 24


class NotePreview(QtWidgets.QWidget):
    """把 `Score` 画成音符条形图。"""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._score = None
        self._unreachable: set[int] = set()
        self._current = -1
        self.setMinimumHeight(160)
        self.setToolTip("横轴为拍数，纵轴为音高；红色表示超出乐器音域的音")

    def set_score(self, score, unreachable_pitches: set[int] | None = None) -> None:
        self._score = score
        self._unreachable = unreachable_pitches or set()
        self._current = -1
        self.update()

    def set_current_note(self, index: int) -> None:
        if index != self._current:
            self._current = index
            self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802 (Qt 命名)
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtGui.QColor("#1e1f22"))

        if self._score is None or not self._score.notes:
            painter.setPen(QtGui.QColor("#9aa0a6"))
            painter.drawText(self.rect(), QtCore.Qt.AlignmentFlag.AlignCenter, "（没有可预览的曲谱）")
            return

        notes = self._score.notes
        total_beats = max(self._score.duration_beat, 1e-6)
        span = MAX_SEMITONE - MIN_SEMITONE + 4
        left, right, top, bottom = 8, self.width() - 8, 8, self.height() - 18
        width, height = max(right - left, 1), max(bottom - top, 1)

        # 参考线：中音 1 / 高音 1 / 低音 1
        painter.setPen(QtGui.QPen(QtGui.QColor("#3c4043"), 1, QtCore.Qt.PenStyle.DotLine))
        for semitone, label in ((0, "中音1"), (12, "高音1"), (-12, "低音1")):
            y = bottom - (semitone - MIN_SEMITONE + 2) / span * height
            painter.drawLine(int(left), int(y), int(right), int(y))
            painter.setPen(QtGui.QColor("#5f6368"))
            painter.drawText(int(left) + 2, int(y) - 2, label)
            painter.setPen(QtGui.QPen(QtGui.QColor("#3c4043"), 1, QtCore.Qt.PenStyle.DotLine))

        for index, note in enumerate(notes):
            if note.pitch is None:
                continue
            x0 = left + note.start_beat / total_beats * width
            x1 = left + (note.start_beat + max(note.duration_beat - 0.05, 0.05)) / total_beats * width
            y = bottom - (note.pitch - MIN_SEMITONE + 2) / span * height
            color = QtGui.QColor("#f28b82") if note.pitch in self._unreachable else QtGui.QColor("#8ab4f8")
            if index == self._current:
                color = QtGui.QColor("#fdd663")
            painter.fillRect(QtCore.QRectF(x0, y - 4, max(x1 - x0, 2), 8), color)

        painter.setPen(QtGui.QColor("#9aa0a6"))
        painter.drawText(int(left), self.height() - 4, f"共 {total_beats:g} 拍")

