# SPEC — 口琴自动演奏宏 v1

- **日期**: 2026-09-25
- **版本**: 1.0（Step 2 产物）
- **状态**: 待 `SPEC_APPROVED`
- **上游依据**: [`DESIGN_SUMMARY_FOR_OPENSPEC.md`](DESIGN_SUMMARY_FOR_OPENSPEC.md)（已获 `APPROVED`）
- **决策依据**: ADR-002（曲谱双格式）、ADR-003（纯 Python 单进程）、ADR-004（个人非商业许可）

本文是**规范性文档**：Step 3 的测试计划与 Step 4 的实现都以本文的条款为准。
凡标注 **【规范性】** 的条目，实现与测试必须逐字满足；标注 **【信息性】** 的条目只是解释。

---

## 1. 范围

### 1.1 v1 交付

1. 单进程桌面应用（`python -m kouqin`），PySide6 界面 + 后台播放线程。
2. 曲谱：文本简谱 `.kq` 的解析与渲染、`.kq.json` 的读写、**MIDI（SMF 0/1）导入**、剪贴板粘贴。
3. 演奏计划编译：音高映射（含修饰键组合）、时值换算、长音切分、修饰键切换处理、移调。
4. 播放：开始/倒计时/暂停/继续/停止/循环/速度（0.5×–2×）/进度显示/急停。
5. 全局热键：`Ctrl+Alt+P`（开始停止）、`Ctrl+Alt+U`（暂停继续）、`Ctrl+Alt+K`（急停）。
   全部可在设置页修改，并提供「检测」按钮当场验证是否被别的程序占用。
6. 设置页与校准页（读写 `config/instrument.json`、`config/settings.json`）。

### 1.2 v1 不做

和弦/多声部、音频合成试听、图片/PDF 谱面识别、云同步、录制模式、多曲目播放列表、自动更新。

### 1.3 完成定义

§10 验收标准全部通过，且 `python -m pytest -q` 全绿。

---

## 2. 术语与单位 【规范性】

| 术语 | 含义 |
|------|------|
| 拍（beat） | 曲谱的时间单位；四分音符 = 1 拍 |
| 毫秒（ms） | 配置与演奏计划的时间单位 |
| 半音偏移 `s` | 相对乐器基准音（`z` 键 = 中音 `1`）的半音数；`s` 可为负 |
| 修饰组合 | 一组同时按住的鼠标键，如 `["left","middle"]`；空数组表示不按 |
| 音名 | 简谱写法，如 `#1'`、`b3,`、`0`（休止） |

单位换算 **【规范性】**：

```text
ms_per_beat = 60000 / (tempo_bpm × speed)
```

`speed` 是播放速度倍率（0.5–2.0），在**编译期**生效（不做运行时变速）。

---

## 3. 数据契约

### 3.1 乐器配置 `config/instrument.json`

**【规范性】** 字段与语义以该文件现有内容为准（v2 schema，已实测校准）：

- `keys[]`：`{ key, degree, octave }`；`key_semitone = 音级半音(degree) + 12 × octave`，
  音级半音 = `{1:0, 2:2, 3:4, 4:5, 5:7, 6:9, 7:11}`。
- `modifiers[]`：`{ button, label, semitone }`；`button ∈ {left, middle, right}`。
- `modifier_sets[]`：`{ buttons[], status, note }`；`status ∈ {verified, assumed}`。
  **组合偏移 = 各键 `semitone` 之和**（不得重复写死在别处）。
- `verified: false` 时禁止进游戏播放（错误码 CP004）。
- 编译器**只使用** `status == "verified"` 的组合。

### 3.2 播放设置 `config/settings.json`

**【规范性】** 三个区块：

| 区块 | 字段 | 语义 |
|------|------|------|
| `playback` | `min_hold_ms` | 单次按下的最短时长下限 |
| | `note_gap_ms` | 同音/相邻音之间的断开时长；也用于长音重触发的段间间隔 |
| | `modifier_lead_ms` | 修饰键比按键**早**按下的时长 |
| | `modifier_tail_ms` | 修饰键比按键**晚**松开的时长 |
| | `countdown_ms` | 「开始」后的倒计时 |
| | `retrigger_long_notes` | 布尔；是否对超长音分段重触发 |
| | `sustain_limit_ms` | 单次按住可维持可闻的最长时间；`null` = 尚未实测 |
| `hotkeys` | `toggle_play` / `pause_resume` / `panic_release` | 组合键字符串，语法 `Mod+...+Key`，`Mod ∈ {Ctrl, Alt, Shift, Win}` |
| `midi` | `reference_note` | MIDI 音高基准（默认 60 = 中音 C） |
| | `reference_semitone` | 上述 MIDI 音高对应的 `s`（默认 0） |
| `notes` | 每个参数一条依据说明 | 与 `playback` 键集合必须一致（回归测试强制） |

**【规范性】** `sustain_limit_ms == null` 时：编译器**不得**切分长音，如实按住整段时值。

### 3.3 曲谱内部模型

**【规范性】**

```python
@dataclass(frozen=True)
class Note:
    start_beat: float
    duration_beat: float
    pitch: int | None      # 相对半音；None 表示休止
    repr: str              # 原始写法，用于错误定位与显示
    tie: bool = False      # 与前一音同高且连奏
    line: int = 1          # 源文件行号（1 起）

@dataclass(frozen=True)
class Score:
    title: str
    tempo_bpm: float
    meter: str             # 如 "4/4"，仅用于显示与小节校验
    transpose: int         # 整体移调半音数
    notes: tuple[Note, ...]
    source: str | None     # 来源文件路径或 "clipboard"/"midi:<path>"
```

**【规范性】** `notes` 按 `start_beat` 升序且不重叠（单音线，无和弦）。

### 3.4 文本简谱 `.kq`

**【规范性】** 文法：

```ebnf
file       = { line } ;
line       = meta | comment | music ;
meta       = "@" name ws value ;
comment    = "#" { 任意字符 } ;   (* 行首的 # 后不紧跟数字时才是注释；见 §13 勘误 E7 *)
music      = { ws | barline | note } ;
barline    = "|" ;
note       = [ "~" ] [ accidental ] degree [ octave ] [ duration ] ;
accidental = "#" | "b" ;
degree     = "0" | "1" | "2" | "3" | "4" | "5" | "6" | "7" ;
octave     = "," | "'" ;                     (* 可重复，如 1'' *)
duration   = { "-" } [ "." ] { "_" } ;       (* 见下求值规则 *)
```

**【规范性】** 元信息：

| 名称 | 必需 | 取值 | 缺省 |
|------|------|------|------|
| `@title` | 否 | 任意非空文本 | `未命名` |
| `@tempo` | 否 | 正数（BPM） | `120` |
| `@meter` | 否 | `分子/分母`，分子分母均正整数 | `4/4` |
| `@key` | 否 | 音名（仅显示） | 空 |
| `@transpose` | 否 | 整数，可负 | `0` |

未知的 `@name` → 错误 KQ002（不静默忽略）。

**【规范性】** 音高求值：

```text
八度偏移 = 12 × ( "'" 个数 − "," 个数 )
音级偏移 = 音级半音(degree)           # degree = 0 表示休止，无音高
变化音   = "#" → +1 ； "b" → −1
pitch    = 音级偏移 + 八度偏移 + 变化音
```

**【规范性】** 时值求值（顺序固定）：

```text
基础 = 1 拍
先加：基础 = 基础 + ("-" 的个数)
再乘：基础 = 基础 × (有 "." 则 1.5，否则 1.0)
再除：基础 = 基础 ÷ 2^("_" 的个数)
```

**【规范性】** 规则与错误：

- `~` 只能出现在**第二个及以后**的音上，且要求前一个音**音高相同**；否则 KQ008。
- 休止符 `0` 不得带 `#`/`b` 或八度标记；否则 KQ005。
- 时值求值结果必须 > 0；否则 KQ006。
- 文件内无任何音符 → KQ010。
- 小节长度与 `@meter` 不符 → **警告** KQ009（不阻断解析）。
- 单音 `|pitch| > 48`（四个八度）→ KQ011。

**【规范性】** 示例（可直接作为测试输入）：

```text
# 小星星
@title 小星星
@tempo 100
@meter 4/4

1 1 5 5 | 6 6 5- | 4 4 3 3 | 2 2 1- |
# 带变化音、附点、休止、连音
3 #4 5. 0 | 6_ 7_ 1'~ 1' |
```

### 3.5 JSON 曲谱 `.kq.json`

**【规范性】** 结构（往返必须无损）：

```json
{
  "version": 1,
  "title": "小星星",
  "tempo_bpm": 100,
  "meter": "4/4",
  "transpose": 0,
  "notes": [
    { "start_beat": 0.0, "duration_beat": 1.0, "pitch": 0, "repr": "1", "tie": false, "line": 6 }
  ]
}
```

**【规范性】** 往返等价：`parse_kq(text)` → `Score` → `dump_json` → `load_json` → `Score`，
两次 `Score` 的 `notes` 逐字段相等（`line` 除外，允许归零）。

### 3.6 MIDI 导入（SMF 0/1）

**【规范性】** 解析要求：

1. 只接受 `MThd` 开头、`format ∈ {0, 1}`；`format 2` → MD002；无 `MThd` → MD001。
2. `division` 必须是以拍为单位的正数（bit15 = 0）；SMPTE（bit15 = 1）→ MD003。
3. 处理 running status、meta 事件 `0x51`（set tempo，默认 500000 µs/拍）、`0x58`（拍号）、`0x2F`（曲尾）。
4. 忽略 channel 10（索引 9，打击轨）的事件。
5. **合并策略**：所有含音符的轨道合并为一条单音线；同一时刻存在多个音时**保留最高音**，
   其余计入 `dropped_notes` 并在界面显示（信息级 MD006）。
6. 时间换算：`拍 = Δtick / division`；tempo 变化时按 `set tempo` 分段累计拍数
   （v1 用首个 tempo 作为 `tempo_bpm`，其余 tempo 变化只影响拍数累加，不写入曲谱）。
7. 音高换算：`s = (midi_note − reference_note) + reference_semitone`。
8. 解析后若存在 `s ∉ [−12, 24]` 的音 → MD005，并在界面提示"可整体移调"。
9. 无任何音符 → MD004。

### 3.7 演奏计划 `runtime/plan.json`（调试产物）

**【规范性】**

```json
{
  "version": 1,
  "title": "小星星",
  "tempo_bpm": 100,
  "speed": 1.0,
  "transpose": 0,
  "source": "scores/小星星.kq",
  "generated_at": "2026-09-25T22:00:00+08:00",
  "params": {
    "min_hold_ms": 40, "note_gap_ms": 30,
    "modifier_lead_ms": 10, "modifier_tail_ms": 10,
    "sustain_limit_ms": null
  },
  "issues": [{ "code": "KQ009", "level": "warning", "beat": 8.0, "message": "第 3 小节长度 3.5 拍" }],
  "notes": [
    { "index": 0, "start_ms": 0, "duration_ms": 600, "pitch": 0, "repr": "1",
      "fingering": { "key": "z", "buttons": [] } }
  ],
  "events": [
    { "t_ms": 0, "op": "key_down", "arg": "z" },
    { "t_ms": 570, "op": "key_up", "arg": "z" }
  ]
}
```

- `op ∈ {key_down, key_up, mouse_down, mouse_up}`；`arg` 为键字符或 `left|middle|right`。
- 该文件**不是**进程间通道（ADR-003），仅供人工核对与排障。

---

## 4. 模块与接口 【规范性】

| 模块 | 公开接口（函数/类） |
|------|---------------------|
| `kouqin.core.pitch` | `degree_semitone(degree) -> int`、`key_semitone(key) -> int`、`modifier_offset(buttons, modifiers) -> int` |
| `kouqin.core.instrument` | `load_instrument(path) -> Instrument`、`reachable(instrument) -> set[int]`、`find_fingering(instrument, target, prefer_buttons=()) -> Fingering \| None` |
| `kouqin.core.score` | `Note`、`Score`、`Issue`、`ScoreError` |
| `kouqin.core.compile` | `compile_plan(score, instrument, settings, *, speed=1.0) -> Plan`（抛 `PlanError(issues)`） |
| `kouqin.scores.kq` | `parse_kq(text: str) -> Score`、`render_kq(score) -> str` |
| `kouqin.scores.json_score` | `load_score_json(path) -> Score`、`dump_score_json(score, path) -> None` |
| `kouqin.scores.midi` | `import_midi(path, reference_note, reference_semitone) -> MidiImportResult` |
| `kouqin.scores.library` | `list_scores(dir) -> list[ScoreEntry]`、`save_score(score, path)`、`delete_score(path)` |
| `kouqin.input.win32` | `InputSender.send(action)`、`release_all()`、`is_injectable() -> bool` |
| `kouqin.player.engine` | `Player(plan, on_progress, on_state, sender)`：`play()` / `pause()` / `resume()` / `stop()` / `panic()` |
| `kouqin.hotkey.win32` | `HotkeyManager(win_id)`：`register(combo, callback) -> bool`、`unregister_all()` |
| `kouqin.settings` | `load_settings(path) -> Settings`、`save_settings(settings, path)` |

**【规范性】** `kouqin/core/`、`kouqin/scores/` 不得 import PySide6 或调用任何系统输入 API。

---

## 5. 编译算法 【规范性】

输入：`Score`、`Instrument`、`Settings`、`speed`。输出：`Plan`（§3.7）。

### 5.1 前置校验

1. `instrument.verified != true` → CP004。
2. `score.notes` 为空 → KQ010。

### 5.2 逐音处理

```text
ms_per_beat = 60000 / (tempo_bpm × speed)
对每个非休止音：
    target      = note.pitch + score.transpose
    fingering   = find_fingering(instrument, target, prefer_buttons=上一个音的 buttons)
    若 fingering 为 None → CP001（带 note.repr 与行号）
    start_ms    = note.start_beat    × ms_per_beat
    duration_ms = note.duration_beat × ms_per_beat
    hold_ms     = max(1, min(duration_ms, max(duration_ms − note_gap_ms, min_hold_ms)))   # §13 勘误 E1
```

### 5.3 候选优先级（`find_fingering`）

依次比较，取第一个最优：

1. `status == verified` 的组合优先（`assumed` 一律不参与）；
2. 鼠标键数量更少者优先（0 > 1 > 2）；
3. **与 `prefer_buttons` 相同**者优先（减少切换）；
4. 键位表顺序靠前者优先。

### 5.4 后处理（顺序固定）

1. **连音合并**：`tie == true` 且音高相同的相邻音合并为一次按住（`hold` 累加）。
2. **长音切分**（见 §13 勘误 E2）：若 `sustain_limit_ms` 非空、`retrigger_long_notes` 为真且
   `hold_ms > sustain_limit_ms`：

   ```text
   gap = note_gap_ms
   段数 n    = ceil((hold_ms + gap) / (sustain_limit_ms + gap))
   每段时长  = (hold_ms − (n−1) × gap) / n      # 毫秒取整，余数并入最后一段
   ```

   段间插入 `gap`，**总跨度恒等于 `hold_ms`**（不会挤到下一个音）；每段独立重新起音。
   否则整段按住。
3. **修饰键切换**（见 §13 勘误 E3、E6）：维护「当前按住的修饰键集合」`held`（初始为空）。
   对每个音的 `need = fingering.buttons`：

   - `need == held` → **不发任何鼠标事件**（组合保持不变，不重复按放）；
   - `need != held` → 先松开 `held \ need`（时间 = **上一个音的 `key_up` + `modifier_tail_ms`**），
     再在 **本音 `key_down` − `modifier_lead_ms`** 按下 `need \ held`。

   ```text
   换修饰所需的最小间隔 = modifier_lead_ms + modifier_tail_ms
   ```

   若相邻两音（**非休止音之间**）的实际间隔不足，则把后一个音及其后续整体**顺延**到满足为止
   （音准优先于节拍），并记录 CP002 警告。休止符不产生事件，也**不中断** `held` 状态。
4. **事件生成**：对每个按下段产生 `key_down` → （保持 `hold_ms`）→ `key_up`；
   修饰键的 `mouse_down` / `mouse_up` 由规则 3 决定（首次按下提前 `modifier_lead_ms`，
   最后一次松开延后 `modifier_tail_ms`）。

### 5.5 不变量（生成后必须校验，违反则拒绝出计划）

1. 所有 `t_ms >= 0`，且 `events` 按 `t_ms` 非递减稳定排序。
2. 同一键/鼠标键在按下状态下不得再次 `*_down`。
3. 计划结束时所有键与鼠标键都处于松开状态。
4. 每个非休止音都有 `fingering`，且 `fingering` 的按键与修饰组合与事件序列一致。

---

## 6. 播放引擎与线程模型 【规范性】

### 6.1 状态机

```text
idle → countdown → playing ⇄ paused → stopped → idle
任一状态 --panic--> idle（并保证所有键已松开）
任一状态 --错误--> error（并保证所有键已松开）
```

### 6.2 线程

- **UI 线程**：全部 Qt 控件；不得执行 sleep、不得调用 `SendInput`。
- **Player 线程**：唯一的计划执行者与注入调用者；从 `queue.Queue` 取命令。
- **进度上报**：Player 线程发出信号（`note_index`, `elapsed_ms`），Qt 以队列方式投递到 UI 线程。
- **急停**：`panic()` 只设置 `threading.Event`；Player 线程在等待循环中**每 ≤ 5 ms** 检查一次，
  立即释放所有按下的键并回到 `idle`。目标：从调用到释放 ≤ 100 ms。

### 6.3 时序推进

- 以 `time.perf_counter()` 建立绝对基准；每个事件睡到 `base + t_ms/1000`。
- 等待策略：剩余 > 2 ms 用 `time.sleep(剩余 − 2ms)`，最后 2 ms 忙等。
- 循环播放：到达末尾后从第一个事件重新开始（不重新倒计时）。

### 6.4 异常安全

任何退出路径（正常结束、stop、panic、异常、进程退出）都必须释放所有按下的键与鼠标键；
以 `try/finally` + `atexit` 双重保证，并由测试覆盖（用假 Sender 记录动作）。

---

## 7. 全局热键 【规范性】

1. 通过 `RegisterHotKey(hwnd, id, modifiers, vk)` 注册，`hwnd` 为主窗口句柄；
   在 Qt 中用 `QAbstractNativeEventFilter` 捕获 `WM_HOTKEY = 0x0312`。
2. 组合键字符串解析：`Ctrl+Alt+P` → `MOD_CONTROL | MOD_ALT` + `P`；
   修饰键名不区分大小写，键名支持 `A-Z`、`0-9`、`F1-F12`。
3. 三个动作：`toggle_play`（在 idle/stopped 时开始，在 playing/countdown/paused 时停止）、
   `pause_resume`、`panic_release`。
4. 注册失败（被其它程序占用）必须在界面明确提示并给出修改入口，不得静默失效。
5. 程序退出时 `UnregisterHotKey` 全部注销。

---

## 8. 界面规格 【规范性】

主窗口三区布局：左侧曲谱库、中部编辑/预览、底部播放控制条；顶部菜单（文件/播放/设置/帮助）。

| 区域 | 要求 |
|------|------|
| 曲谱库 | 列：曲名、音符数、时长、映射状态（`可完整演奏` 或 `N 个音不可达`）；支持双击打开 |
| 编辑器 | 纯文本；输入后 300 ms 防抖解析；错误行左侧标红 + 消息面板显示 `行号 + 错误码 + 说明` |
| 预览 | 音符条形图（横轴拍、纵轴音高）；不可达音高标红；可切换查看编译后事件序列摘要 |
| 播放控制条 | 开始（倒计时可配置）、暂停/继续、停止、循环开关、速度 0.5×–2×、移调 ±12、进度条与当前音符高亮 |
| 导入/导出 | 菜单与拖拽均支持 `.kq` / `.kq.json` / `.mid`；支持从剪贴板粘贴简谱 |
| 设置页 | 键位表（增删改）、修饰键半音数与组合、播放参数、长音重触发开关、热键 |
| 校准页 | 逐项「试拍」；用户按游戏内标注读数回填 `instrument.json` 并置 `verified: true` |
| 状态栏 | 状态（未启动/就绪/倒计时/播放中/已暂停/错误）+ 当前音符序号 |

**【规范性】** `instrument.verified == false` 时「开始」按钮禁用，提示：
`请先在「校准」页确认三个鼠标键的音程`。

**【规范性】** 存在 `error` 级问题（CP001/CP004/KQ010 等）时禁止播放；
仅 `warning` 级问题（KQ009/CP002）允许播放但必须在消息面板列出。

---

## 9. 错误码 【规范性】

| 码 | 级别 | 含义 |
|----|------|------|
| KQ002 | error | 未知元信息名 |
| KQ003 | error | 元信息值非法（tempo ≤ 0 / transpose 非整数 / meter 或 key 格式错误） |
| KQ004 | error | 无法解析的音符标记 |
| KQ005 | error | 休止符带变化音或八度标记 |
| KQ006 | error | 时值过小：求值结果 < 1/64 拍（见 §13 勘误 E4；原「≤ 0」为死码） |
| KQ008 | error | `~` 出现在首音或与前音音高不同 |
| KQ010 | error | 曲谱内没有音符 |
| KQ011 | error | 音高超出 ±48 半音 |
| KQ009 | warning | 小节长度与 `@meter` 不符 |
| CP001 | error | 音高不可达（乐器音域或组合不足） |
| CP002 | warning | 换修饰键的时间不足，已顺延后一音 |
| CP003 | error | 计划事件冲突（同键未释放又按下） |
| CP004 | error | 乐器配置未校准（`verified: false`） |
| MD001 | error | 不是有效 MIDI（缺 MThd） |
| MD002 | error | 不支持的 MIDI 格式（仅 0/1） |
| MD003 | error | 不支持的 division（SMPTE） |
| MD004 | error | MIDI 内没有音符 |
| MD005 | error | 导入后有音高超出乐器音域 |
| MD006 | info | 和弦被降为单音（报告丢弃数量） |

---

## 10. 验收标准 【规范性】

| 编号 | 标准 | 验证方式 |
|------|------|----------|
| A1 | `.kq` 解析：附点、休止、变化音、八度、连音、小节线、注释、元信息全部按 §3.4 求值 | 单元测试逐条断言 `pitch` 与 `duration_beat` |
| A2 | 往返无损：`.kq` → `Score` → `.kq.json` → `Score` 逐音相等 | 单元测试 |
| A3 | 音高映射：`find_fingering` 对 −12…24 全部返回值，且优先级符合 §5.3 | 单元测试（含 `prefer_buttons` 的连续性） |
| A4 | 不可达音报错：低音区以外的音（如 `s = 30`）返回 CP001 且带行号 | 单元测试 |
| A5 | 编译时序：给定 BPM/拍号，事件时间与手算结果完全一致 | 单元测试 |
| A6 | 长音切分：`sustain_limit_ms=2000` 时，3000 ms 的音被切成 2 段且总时长不变 | 单元测试 |
| A7 | 修饰键切换：相邻音组合不同时，事件顺序为「松键 → 换修饰 → 按键」 | 单元测试 |
| A8 | 计划不变量：§5.5 四条在随机生成的曲谱上恒成立 | 属性式单元测试（固定随机种子） |
| A9 | MIDI 导入：对样例 `.mid`（format 1、多轨、含打击轨与和弦）输出单音线、丢弃数正确 | 单元测试 + 样例文件 |
| A10 | 异常安全：任何停止路径后，假 Sender 记录中所有键都成对闭合 | 单元测试 |
| A11 | 游戏内可演奏：≥3 首曲目（含升降音、休止、长音）音高与时值主观正确 | 手动验收清单 |
| A12 | 控制可靠：停止 ≤100 ms 生效；停止后不留按下的键 | 手动验收 |
| A13 | 未校准保护：`verified: false` 时无法开始播放 | 手动验收 + 单元测试 |
| A14 | 错误可见：语法错误与不可达音在界面报出行号与错误码 | 手动验收 |

---

## 11. 未决项（不影响 Step 3 测试计划编写）

| 编号 | 内容 | 影响 | 处理 |
|------|------|------|------|
| U6 | ~~长音衰减时间常数~~ | — | ✅ 已实测（2026-09-25，P0-7）：按住 2–10 秒正常，**约 10 秒起明显衰减、很快听不见**（此时按键仍被按住）→ `sustain_limit_ms = 6000`（留 4 秒余量）；由 C-04/C-05/C-05b 覆盖 |
| U5 | 按键到出声的延迟 | `countdown_ms` 是否需要加大 | 首曲回归时主观校准 |
| U11 | 极快同音连打是否吞音 | `note_gap_ms` 下限 | 用到快节奏曲子时复测 |
| U10 | 换修饰键时同键是否重新触发 | 无（设计已不依赖：一律重按，见 §5.4-3） | 保持不依赖 |

---

## 12. 与上游文档的关系

- 设计（为什么这样做）：`DESIGN_SUMMARY_FOR_OPENSPEC.md`
- 本文（做什么、验收标准）：`SPEC.md`
- 测试计划（怎么测）：`TEST_PLAN.md`（Step 3 产出）
- 决策记录：`../harness/DECISIONS.md`（ADR-001…004）

---

## 13. 勘误记录（v1.0 → v1.1，2026-09-25）

Step 3 编写测试用例时发现 4 处边界定义有缺陷，经用户确认后修订（不另开 ADR）。

| 编号 | 原条款 | 问题 | 修订 |
|------|--------|------|------|
| E1 | §5.2 `hold_ms = max(时长 − 间隔, 最短时长)` | 短音符（如 30 ms）会被拉长到 `min_hold_ms`（40 ms），**超过音符自身时值**，与下一音重叠并违反 §5.5 不变量 | 改为 `max(1, min(时长, max(时长 − 间隔, 最短时长)))`：最短按时长不得突破音符自身时值；该式在「时长 < 最短时长」时也唯一确定 |
| E2 | §5.4-2 `n = ceil(hold / sustain)`，段间插 `gap` | 空隙未计入预算，切分后总跨度 = `hold + (n−1)×gap`，**超出原时值**并侵入下一音 | 改为按含空隙计算段数，每段 = `(hold − (n−1)×gap) / n`，总跨度恒等于 `hold` |
| E3 | §5.4-3「相邻两音」 | 未定义是否跨越休止符，字面实现会**漏做修饰键切换**，导致音高错误 | 明确为「相邻的两个**非休止**音」；休止不中断修饰键状态的延续 |
| E4 | §9 KQ006「时值 ≤ 0」 | 求值规则含除以 `2^n`，结果**恒为正**，该错误码无法触发（死码） | 改为「时值过小：< 1/64 拍」，编号保留；KQ007 继续留空 |

以下两条是编写测试时暴露的**实现二义性**（E5、E6），一并并入正文：

| 编号 | 原条款 | 问题 | 修订 |
|------|--------|------|------|
| E5 | §5.5-1「所有 `t_ms ≥ 0`」与 §5.4-4「修饰键提前 `modifier_lead_ms` 按下」 | 若**首个音**即需按住修饰键，`mouse_down` 会落在 `t < 0`（如 −10 ms），与不变量冲突 | 若最早事件为负，则**整个计划后移**使最早事件为 0；计划新增字段 `offset_ms` 记录位移，`notes[].start_ms` 一并平移 |
| E6 | §5.4-3 原公式 `tail + (|旧\新| + |新\旧|) × lead` | 与「组合相同则不重按」的实现模型不一致（按钮数加权会让同组合也付出代价），且未定义松开/按下的确切时刻 | 改为「相同组合不动作」模型，逐条给出松开与按下时刻，最小间隔 = `lead + tail` |
| E7 | §3.4 注释与升号都用 `#` | 行首 `#4` 既可读作「注释」也可读作「升 4」，文法二义，实现无法判定 | 明确：**行首的 `#` 若紧跟数字（0–7）则按升号处理**，否则整行为注释；行内其它位置的 `#` 必须是升号，否则 KQ004 |

**影响范围**：§5.2、§5.4、§5.5、§9 与测试计划的 C-01/C-04/C-07/C-08/C-09/K-16/R-01/R-02。
