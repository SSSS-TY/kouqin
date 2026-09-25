"""文本简谱 `.kq` 的解析与渲染（SPEC §3.4，含勘误 E4/E7）。

语法要点：

- 元信息 `@name value`；注释 `#`；小节线 `|`；
- 音符 `[~][#|b]?[0-7][',]*[-._]*`，`~` 表示「连到前一个音」；
- 行首的 `#` 后紧跟数字时按升号处理，否则整行是注释（勘误 E7）。
"""

from __future__ import annotations

import re
from pathlib import Path

from kouqin.core.pitch import degree_semitone, split_pitch
from kouqin.core.score import ERROR, WARNING, Issue, Note, Score, ScoreError

TOKEN_RE = re.compile(
    r"^(?P<tie>~?)(?P<accidental>#|b)?(?P<degree>[0-7])(?P<octave>[',]*)(?P<duration>[-._]*)$"
)
METER_RE = re.compile(r"^(?P<num>\d+)/(?P<den>\d+)$")

MAX_PITCH = 48          # 勘误 E7/§3.4：超过 ±48 半音视为非法
MIN_DURATION = 1 / 64   # 勘误 E4：时值下限

META_NAMES = {"title", "tempo", "meter", "key", "transpose"}


def parse_kq(text: str, source: str | None = None) -> Score:
    """解析简谱文本；致命错误抛 `ScoreError`，非致命问题写入 `Score.issues`。"""
    meta: dict[str, str] = {}
    errors: list[Issue] = []
    warnings: list[Issue] = []
    notes: list[Note] = []

    beat = 0.0
    bar_beat = 0.0
    previous_pitch: int | None = None
    has_previous = False

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#") and not (len(line) > 1 and line[1].isdigit()):
            continue
        if line.startswith("@"):
            _parse_meta(line, line_number, meta, errors)
            continue
        for token in line.split():
            if token == "|":
                numerator = _meter_numerator(meta)
                if numerator and abs(bar_beat - numerator) > 1e-9:
                    warnings.append(
                        Issue("KQ009", WARNING, f"小节长度为 {bar_beat:g} 拍，与 {numerator}/… 不符", line=line_number, beat=beat)
                    )
                bar_beat = 0.0
                continue

            match = TOKEN_RE.match(token)
            if match is None:
                errors.append(Issue("KQ004", ERROR, f"无法解析的音符标记：{token!r}", line=line_number))
                continue

            degree = int(match.group("degree"))
            accidental = match.group("accidental")
            octave_marks = match.group("octave")
            is_tie = bool(match.group("tie"))

            if degree == 0:
                if accidental or octave_marks:
                    errors.append(Issue("KQ005", ERROR, f"休止符不能带变化音或八度标记：{token!r}", line=line_number))
                    continue
                pitch = None
            else:
                pitch = degree_semitone(degree)
                if accidental == "#":
                    pitch += 1
                elif accidental == "b":
                    pitch -= 1
                ups = octave_marks.count("'")
                downs = octave_marks.count(",")
                pitch += 12 * (ups - downs)
                if abs(pitch) > MAX_PITCH:
                    errors.append(Issue("KQ011", ERROR, f"音高超出可表示范围（±{MAX_PITCH} 半音）：{token!r}", line=line_number))
                    continue

            if is_tie and (not has_previous or previous_pitch != pitch or pitch is None):
                errors.append(
                    Issue("KQ008", ERROR, f"连音标记 ~ 必须紧跟在同音高之后：{token!r}", line=line_number)
                )
                continue

            duration = _duration_of(match.group("duration"), token, line_number, errors)
            if duration is None:
                continue

            notes.append(
                Note(
                    start_beat=beat,
                    duration_beat=duration,
                    pitch=pitch,
                    repr=token,
                    tie=is_tie,
                    line=line_number,
                )
            )
            beat += duration
            bar_beat += duration
            previous_pitch = pitch
            has_previous = True

    if errors:
        raise ScoreError(errors)
    if not notes:
        raise ScoreError([Issue("KQ010", ERROR, "曲谱内没有任何音符")])

    tempo = 120.0
    if "tempo" in meta:
        try:
            tempo = float(meta["tempo"])
        except ValueError:
            tempo = 120.0
    transpose = int(meta.get("transpose", "0"))
    meter = meta.get("meter", "4/4")
    title = meta.get("title", "未命名")

    return Score(
        title=title,
        tempo_bpm=tempo,
        meter=meter,
        transpose=transpose,
        notes=tuple(notes),
        source=source,
        issues=tuple(warnings),
    )


def parse_kq_file(path: str | Path) -> Score:
    """读取 `.kq` 文件（`source` 记录为文件路径字符串）。"""
    path = Path(path)
    return parse_kq(path.read_text(encoding="utf-8"), source=str(path))


def _meter_numerator(meta: dict[str, str]) -> int | None:
    match = METER_RE.match(meta.get("meter", ""))
    return int(match.group("num")) if match else None


def _parse_meta(line: str, line_number: int, meta: dict[str, str], errors: list[Issue]) -> None:
    parts = line[1:].split(maxsplit=1)
    name = parts[0] if parts else ""
    value = parts[1].strip() if len(parts) > 1 else ""
    if name not in META_NAMES:
        errors.append(Issue("KQ002", ERROR, f"未知的元信息：@{name}", line=line_number))
        return
    if not value:
        errors.append(Issue("KQ003", ERROR, f"元信息 @{name} 缺少取值", line=line_number))
        return
    if name == "tempo":
        try:
            if float(value) <= 0:
                raise ValueError
        except ValueError:
            errors.append(Issue("KQ003", ERROR, f"@tempo 必须是正数：{value!r}", line=line_number))
            return
    elif name == "transpose":
        try:
            int(value)
        except ValueError:
            errors.append(Issue("KQ003", ERROR, f"@transpose 必须是整数：{value!r}", line=line_number))
            return
    elif name == "meter":
        match = METER_RE.match(value)
        if match is None or int(match.group("num")) <= 0 or int(match.group("den")) <= 0:
            errors.append(Issue("KQ003", ERROR, f"@meter 必须是 分子/分母 形式且为正：{value!r}", line=line_number))
            return
    meta[name] = value


def _duration_of(suffix: str, token: str, line_number: int, errors: list[Issue]) -> float | None:
    dashes = suffix.count("-")
    has_dot = "." in suffix
    underscores = suffix.count("_")
    if suffix.replace("-", "").replace(".", "").replace("_", ""):
        errors.append(Issue("KQ004", ERROR, f"时值标记非法：{token!r}", line=line_number))
        return None
    if suffix.count(".") > 1:
        errors.append(Issue("KQ004", ERROR, f"附点只能有一个：{token!r}", line=line_number))
        return None
    value = (1 + dashes) * (1.5 if has_dot else 1.0) / (2 ** underscores)
    if value < MIN_DURATION:
        errors.append(Issue("KQ006", ERROR, f"时值过小（< 1/64 拍）：{token!r}", line=line_number))
        return None
    return value


def _duration_suffix(beats: float) -> str:
    """把拍数还原成 `-` / `.` / `_` 后缀（取最短写法）。"""
    best: str | None = None
    for dashes in range(0, 9):
        for dot in (False, True):
            for underscores in range(0, 7):
                value = (1 + dashes) * (1.5 if dot else 1.0) / (2 ** underscores)
                if abs(value - beats) < 1e-9:
                    text = "-" * dashes + ("." if dot else "") + "_" * underscores
                    if best is None or len(text) < len(best):
                        best = text
    if best is None:
        raise ValueError(f"无法用简谱时值标记表示 {beats} 拍")
    return best


def _format_pitch(pitch: int) -> str:
    degree, accidental, octave = split_pitch(pitch)
    accidental_text = {1: "#", -1: "b", 0: ""}[accidental]
    octave_text = "'" * octave if octave > 0 else "," * (-octave)
    return f"{accidental_text}{degree}{octave_text}"


def render_kq(score: Score) -> str:
    """把曲谱渲染回 `.kq` 文本（再解析应得到等价的音符）。"""
    lines = [
        f"@title {score.title}",
        f"@tempo {score.tempo_bpm:g}",
        f"@meter {score.meter}",
    ]
    if score.transpose:
        lines.append(f"@transpose {score.transpose}")
    lines.append("")

    tokens = []
    for note in score.notes:
        suffix = _duration_suffix(note.duration_beat)
        if note.pitch is None:
            tokens.append("0" + suffix)
        else:
            tokens.append(("~" if note.tie else "") + _format_pitch(note.pitch) + suffix)
    lines.append(" ".join(tokens))
    return "\n".join(lines) + "\n"

