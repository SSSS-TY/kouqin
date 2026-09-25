# TEST_PLAN — 口琴自动演奏宏 v1

- **日期**: 2026-09-25
- **版本**: 1.0（Step 3 产物）
- **状态**: 待 `TEST_PLAN_APPROVED`
- **上游依据**: [`SPEC.md`](SPEC.md) v1.0（已获 `SPEC_APPROVED`）
- **验收映射**: 本计划每条用例都标注它覆盖 SPEC §10 的哪一条验收标准（A1–A14）

---

## 1. 目标与范围

| 目标 | 说明 |
|------|------|
| 正确性 | 曲谱解析、音高映射、演奏编译的结果与 SPEC 逐条一致 |
| 边界与错误 | 20 个错误码（KQ/CP/MD）都有可复现的触发用例 |
| 安全性 | 任何停止路径都不留按下的键（假 Sender 全程记录） |
| 可维护性 | 实测口径（`instrument.json` / `settings.json`）被回归测试钉住 |

**测试分层**

| 层 | 范围 | 能否自动化 |
|----|------|-----------|
| 单元测试 | `kouqin/core`、`kouqin/scores` | ✅ 全部自动化 |
| 引擎测试 | `kouqin/player`（真实时钟 + 假 Sender + 极短计划） | ✅ 自动化，只断言顺序与状态 |
| 契约/回归 | 配置与 `plan.json` schema、golden 计划 | ✅ 自动化 |
| 界面冒烟 | 主窗口能构造、能加载曲谱 | ✅ 自动化（无 PySide6 时跳过） |
| 游戏内验收 | A11–A14 的实机行为 | ❌ 手动清单（§7） |

---

## 2. 目录结构

```text
tests/
  unit/                      单元与引擎测试（现有 4 个文件保留）
  fixtures/
    scores/                  .kq 样例（含各错误码的坏例）
    midi/                    样例 .mid（由脚本生成并入库）
    expected/                golden 期望产物
  manual/
    ACCEPTANCE.md            游戏内验收清单与记录模板
```

**【规范性】** 测试不得访问网络、不得向真实窗口注入输入、不得写 `runtime/` 之外的文件。

---

## 3. 环境与前置

- Python 3.13.12、pytest 9.1.1（已安装，无需新增依赖）。
- 单元与引擎测试**不需要游戏、不需要 PySide6**（`kouqin/core`、`kouqin/scores` 禁止依赖 Qt）。
- 界面冒烟测试用 `pytest.importorskip("PySide6")`，无头环境跳过而非失败。
- 命令：`python -m pytest -q`（全量）、`python -m pytest tests/unit -q`（定向）。

---

## 4. 样例素材

| 文件 | 内容要点 | 用途 |
|------|----------|------|
| `scores/simple.kq` | 小星星 32 拍，4/4 | golden 计划、往返测试 |
| `scores/advanced.kq` | 变化音 `#4`/`b3`、附点 `5.`、休止 `0`、连音 `1'~ 1'`、八度 `1,`/`1''`、注释、`@transpose 2` | A1 全覆盖 |
| `scores/bad_meta_name.kq` | `@foo 1` | KQ002 |
| `scores/bad_meta_value.kq` | `@tempo 0` | KQ003 |
| `scores/bad_note.kq` | `9`、`1x` | KQ004 |
| `scores/bad_rest_mark.kq` | `#0`、`0'` | KQ005 |
| `scores/bad_tie.kq` | `~1 2~` | KQ008 |
| `scores/empty.kq` | 仅元信息、无音符 | KQ010 |
| `scores/bad_range.kq` | `1''''`（48 半音以上） | KQ011 |
| `scores/bad_meter.kq` | `@meter 4/4` 但小节只有 3 拍 | KQ009（警告） |
| `midi/sample_multi.mid` | format 1：旋律轨 + 低音轨 + channel 10 打击轨 + 一处和弦 | M-01…M-07 |
| `midi/sample_format0.mid` | format 0 单轨 + running status | M-02 |
| `midi/bad_format2.mid`、`bad_smpte.mid`、`no_notes.mid`、`not_midi.bin` | format 2 / SMPTE / 无音符 / 非 MIDI | MD001–MD004 |
| `expected/simple.plan.json` | `simple.kq` + 固定参数（tempo=100、speed=1.0、transpose=0、`sustain_limit_ms=null`）的完整计划 | golden |

**【规范性】** 二进制 `.mid` 由 `tools/make_test_midi.py` 生成并**入库**；
用例 `M-00` 会重新生成到内存并与入库文件逐字节比较，防止素材被误改。

---

## 5. 测试用例清单

### 5.1 音高与乐器映射

| ID | 覆盖 | 输入 | 期望 |
|----|------|------|------|
| P-01 | A3 | `degree_semitone(1..7)` | `0,2,4,5,7,9,11` |
| P-02 | A3 | `key_semitone` 对 8 个键 | `0,2,4,5,7,9,11,12` |
| P-03 | A3 | `modifier_offset` 对 6 种组合 | `0,-12,1,12,-11,13` |
| P-04 | A3 | `reachable(instrument)` | 含 `-12..24` 全部 37 个半音 |
| P-05 | A3 | `find_fingering(s)` 遍历 `-12..24` | 全部非 `None`，且 `key_semitone + offset == s` |
| P-06 | A4 | `find_fingering(30)`、`(-17)` | `None` |
| P-07 | A3 | `s = 0` | 选 `z` + 空组合（不按鼠标键优先） |
| P-08 | A3 | `s = -12` 且 `prefer_buttons=("left",)` | 选 `left`（与上一音一致，不切换） |
| P-09 | A3 | 构造"1 键与 2 键组合都可达成"的临时配置 | 选 1 键组合 |
| P-10 | A3 | 把 `["middle","right"]` 设为 `assumed` 的临时配置 | `s = 25` 变为不可达 |
| P-11 | A4 | `verified: false` 的临时配置 + `compile_plan` | 抛 `PlanError`，含 CP004 |

### 5.2 `.kq` 解析

| ID | 覆盖 | 输入（片段） | 期望 |
|----|------|--------------|------|
| K-01 | A1 | `1` | `pitch=0, duration=1.0` |
| K-02 | A1 | `5-`、`5--` | `2.0`、`3.0` |
| K-03 | A1 | `5.`、`5-.` | `1.5`、`3.0`（先加后乘） |
| K-04 | A1 | `5_`、`5__`、`5_.` | `0.5`、`0.25`、`0.75`（最后除） |
| K-05 | A1 | `#1`、`b3` | `1`、`3` |
| K-06 | A1 | `1'`、`1''`、`1,`、`1,,` | `12`、`24`、`-12`、`-24` |
| K-07 | A1 | `0` | `pitch is None`，仍占用时值 |
| K-08 | A1 | `1 \| 2`、多余空白与换行 | 时间不受影响 |
| K-09 | A1 | 含 `#` 注释行 | 被忽略，后续行号仍正确 |
| K-10 | A1 | `simple.kq` 全文 | `tempo=100`、`meter=4/4`、音符数与时值总和符合预期 |
| K-11 | A1 | 缺 `@tempo` / `@transpose` / `@title` | 缺省 `120` / `0` / `未命名` |
| K-12 | A1 | `advanced.kq` 全文 | 逐音断言变化音、附点、休止、连音 `tie=True`、八度、`@transpose=2` |
| K-13 | A4 | `1 1~` | 第二个音 `tie=True` |
| K-14 | A4 | `bad_tie.kq` | KQ008，`line` 指向出错行 |
| K-15 | A4 | `bad_meta_name.kq` | KQ002 |
| K-16 | A4 | `bad_meta_value.kq`、`@transpose 1.5`、`@meter 4/0` | KQ003 |
| K-17 | A4 | `bad_note.kq` | KQ004，`repr` 保留原文 |
| K-18 | A4 | `bad_rest_mark.kq` | KQ005 |
| K-19 | A4 | `empty.kq` | KQ010 |
| K-20 | A4 | `bad_range.kq` | KQ011 |
| K-21 | A4 | `bad_meter.kq` | 解析成功但 `issues` 含 KQ009（warning） |
| K-22 | A1 | `render_kq(parse_kq(x))` | 与 `x` 的规范化形式一致 |

### 5.3 JSON 往返

| ID | 覆盖 | 输入 | 期望 |
|----|------|------|------|
| J-01 | A2 | `advanced.kq` → `Score` → JSON → `Score` | `notes` 逐字段相等（除 `line`） |
| J-02 | A2 | 含 `pitch=None` 的休止 | 往返后仍为 `None` |
| J-03 | A2 | 浮点时值 `0.25`、`1.5` | 往返后精确相等 |

### 5.4 MIDI 导入

| ID | 覆盖 | 输入 | 期望 |
|----|------|------|------|
| M-00 | A9 | 重新生成样例并比对入库文件 | 逐字节相等 |
| M-01 | A9 | `sample_multi.mid` | 音符按时间升序且不重叠 |
| M-02 | A9 | `sample_format0.mid` | 正确解析（含 running status） |
| M-03 | A9 | `sample_multi.mid` 的打击轨 | channel 10 事件全部被忽略 |
| M-04 | A9 | 和弦处 | 保留最高音，`dropped_notes == 1`，产生 MD006(info) |
| M-05 | A9 | tempo 默认 500000 与显式 400000 | `tempo_bpm` 分别为 120 与 150 |
| M-06 | A9 | division=480，Δtick 已知 | `start_beat = Δtick / 480` 精确匹配 |
| M-07 | A9 | 参考音 `60→0` 与 `62→0` | 后者整体低 2 个半音（参考音可配） |
| M-08 | A4 | 四个坏样例 | MD002 / MD003 / MD004 / MD001 |
| M-09 | A4 | 含 `s = 30` 的 MIDI | MD005（错误级）并建议移调 −12 |

### 5.5 演奏计划编译

| ID | 覆盖 | 输入 | 期望 |
|----|------|------|------|
| C-01 | A5 | `simple.kq`，tempo=100，speed=1.0 | 每音 `start_ms/duration_ms` 与手算一致（0/600、600/600…） |
| C-02 | A5 | 同上但 speed=2.0 | 所有时间减半（`ms_per_beat=300`） |
| C-03 | A5 | `@transpose 2` | 音高整体 +2 并重新映射指法 |
| C-04 | A6 | 单音 3000 ms，`sustain_limit_ms=2000` | 切 2 段，总跨度仍为 3000 ms，段间 30 ms 断开 |
| C-05 | A6 | 同上但 `sustain_limit_ms=null` | 单段按住 3000 ms |
| C-06 | A6 | `retrigger_long_notes=false` | 不切分 |
| C-07 | A7 | 组合由 `()` 变为 `("middle",)` | 顺序：`key_up` → `mouse_down(middle)` → `key_down` |
| C-08 | A7 | 组合由 `("left","middle")` 变为 `()` | 顺序：`key_up` → `mouse_up(left)` → `mouse_up(middle)` → `key_down` |
| C-09 | A7 | 两音间隔小于所需切换时间 | 后一音顺延，`issues` 含 CP002，计划仍满足不变量 |
| C-10 | A5 | 连音 `1 1~` | 合并为单段按住 |
| C-11 | A4 | 移调后超出音域 | `PlanError` 含 CP001 与出错的 `repr`/`line` |
| C-12 | A8 | 每个非休止音的 `fingering` | 与事件序列中的键/鼠标键完全一致 |
| C-13 | A5 | `params` 区块 | 与 `settings.json` 的 `playback` 一致 |
| C-14 | 性能 | 2000 音合成曲谱 | 编译 < 1000 ms |

### 5.6 播放引擎与注入

**【规范性】** 引擎测试用**真实时钟**但计划总长 ≤ 50 ms，只断言**事件顺序与最终状态**，
不断言精确触发时刻（避免抖动导致 flaky）。真实注入由**假 Sender**（记录动作）替代。

| ID | 覆盖 | 场景 | 期望 |
|----|------|------|------|
| E-01 | A10 | 播放 6 事件的短计划 | 假 Sender 收到全部动作，顺序与计划一致 |
| E-02 | A10 | 播放中途 `stop()` | 剩余事件不再执行；所有键成对闭合 |
| E-03 | A10 | 播放中途 `panic()` | 从调用到释放 ≤ 100 ms；状态回 `idle` |
| E-04 | A10 | 假 Sender 抛 `OSError` | 进入 `error` 状态且所有键已释放 |
| E-05 | A10 | `pause()` → `resume()` | 暂停期间无新事件；恢复后继续剩余事件 |
| E-06 | A10 | 执行完毕后再 `play()` | 从头开始（不重复倒计时） |
| E-07 | A10 | 循环模式播放短计划 | 到达末尾后重新开始，`loop_count` 递增 |
| E-08 | A10 | `atexit` 路径 | 所有键被释放 |
| E-09 | — | 状态迁移序列 | 符合 SPEC §6.1 状态机，无非法跳转 |

### 5.7 契约与配置回归

| ID | 覆盖 | 场景 | 期望 |
|----|------|------|------|
| G-01 | A3 | 现有 `instrument.json` 断言 | 保持通过 |
| G-02 | A3 | `modifier_sets` 全为 `verified` | 通过（新增未实测组合会失败） |
| G-03 | A2 | `settings.json` 每个参数都有说明 | 通过（现覆盖 `midi.*`） |
| G-04 | A2 | `settings.json` 含未知字段 | `load_settings` 不报错（向前兼容） |
| G-05 | A2 | `settings.json` 缺字段 | 补默认值 + warning，不崩溃 |
| G-06 | A2 | `plan.json` schema | 字段齐全、`op` 合法、`t_ms` 非递减 |
| G-07 | A5 | golden：`simple.kq` + 固定参数 | 与 `expected/simple.plan.json` 逐事件相等 |

### 5.8 随机化与不变量

| ID | 覆盖 | 场景 | 期望 |
|----|------|------|------|
| R-01 | A8 | 固定种子生成 200 首随机曲谱（音高 ∈ −12..24、时值 ∈ 1/8..4 拍、`transpose` ∈ −3..3） | SPEC §5.5 四条不变量恒成立 |
| R-02 | A8 | 同上，随机 `sustain_limit_ms` ∈ 500..3000 | 切分后仍满足不变量，每段 ≤ 上限 |
| R-03 | A8 | 同上，随机 `speed` ∈ 0.5..2.0 | 时间单调、无重叠 |
| R-04 | A8 | 抽 20 首做 `.kq` ↔ `.kq.json` 往返 | 逐音相等 |

---

## 6. 覆盖矩阵（SPEC §10 → 用例）

| 验收标准 | 覆盖用例 |
|----------|----------|
| A1 `.kq` 解析 | K-01…K-12、K-22 |
| A2 往返无损 | J-01…J-03、G-03…G-05 |
| A3 音高映射 | P-01…P-05、P-07…P-10、G-01、G-02 |
| A4 不可达与错误报出 | P-06、P-11、K-13…K-21、M-08、M-09、C-11 |
| A5 编译时序 | C-01…C-03、C-10、C-13、G-07 |
| A6 长音切分 | C-04…C-06、R-02 |
| A7 修饰键切换 | C-07…C-09 |
| A8 计划不变量 | C-12、R-01…R-04 |
| A9 MIDI 导入 | M-00…M-07 |
| A10 异常安全 | E-01…E-08 |
| A11 游戏内可演奏 | MAN-01…MAN-03 |
| A12 控制可靠 | MAN-04、MAN-07、E-02、E-03 |
| A13 未校准保护 | P-11、MAN-05 |
| A14 错误可见 | MAN-06、K-14…K-21 |

---

## 7. 手动验收清单（游戏机 B）

记录模板写入 `tests/manual/ACCEPTANCE.md`，每条都要填「观察结果 + 是否通过」。

| ID | 步骤 | 判据 | 覆盖 |
|----|------|------|------|
| MAN-01 | 导入 `simple.kq`，训练场播放 | 旋律可辨认、节奏均匀 | A11 |
| MAN-02 | 播放 `advanced.kq` | 变化音、附点、休止、连音都听得出，无错音 | A11 |
| MAN-03 | 播放含 ≥2 拍长音的曲目 | 长音不消失；开启重触发后无明显「断气」 | A11 |
| MAN-04 | 播放中按停止、按 `Ctrl+Alt+L` | 立即停声，不残留按下的键 | A12 |
| MAN-05 | 把 `instrument.json` 的 `verified` 改为 `false` | 「开始」禁用并给出提示 | A13 |
| MAN-06 | 故意写错一行简谱 | 界面标红并显示行号 + 错误码 | A14 |
| MAN-07 | 用 `Ctrl+Alt+P` / `Ctrl+Alt+U` 控制播放 | 生效，且不触发游戏内动作 | A12 |

---

## 8. 规格勘误建议（**需用户确认**）

写用例时发现 SPEC v1.0 有 4 处边界定义会让实现二义化。**请与 `TEST_PLAN_APPROVED` 一起确认**（编号 E1–E4）。

| 编号 | SPEC 现状 | 问题 | 建议修订 |
|------|-----------|------|----------|
| E1 | §5.2 `hold_ms = max(duration_ms − note_gap_ms, min_hold_ms)` | 音符很短（如 30 ms）而 `min_hold_ms=40` 时，按住时长**超过音符本身**，会与下一音重叠，违反 §5.5 不变量（CP003） | 改为 `hold_ms = clamp(duration_ms − note_gap_ms, min_hold_ms, duration_ms)`，且 `hold_ms ≥ 1 ms`：最短按时长不得突破音符自身时值 |
| E2 | §5.4-2 切分 `n = ceil(hold_ms / sustain_limit_ms)`，段间插 `note_gap_ms` | 段间空隙未计入预算，总跨度变成 `hold_ms + (n−1)×gap`，**超出原时值**并可能侵入下一个音 | 改为按含空隙计算：`n = ceil((hold_ms + gap) / (sustain + gap))`，每段 = `(hold_ms − (n−1)×gap) / n`，总跨度恒等于 `hold_ms` |
| E3 | §5.4-3「相邻两音的 `buttons` 不同时」 | 未定义「相邻」是否跨越休止符：若两音之间有休止，按字面会漏做修饰键切换 | 明确为「相邻的**两个非休止音**」；休止符不产生事件，也不中断修饰键状态的延续 |
| E4 | §9 错误码 KQ006「时值求值结果 ≤ 0」 | 由 §3.4 求值规则（除 `2^n`）可知该结果恒为正，此码**无法触发**（死码） | 把 KQ006 改为「时值过小：结果 < 1/64 拍」（捕捉 `_____` 之类输入错误），编号保留；KQ007 继续留空 |

**【规范性】** 确认后，Step 4 开始时同步修订 `SPEC.md`，并在 `DECISIONS.md` 记为文档勘误（不新开 ADR）。
受影响用例：E1 → C-01/C-09/R-01；E2 → C-04/R-02；E3 → C-07/C-08；E4 → K-16。

---

## 9. 红例策略与完成判据

**【规范性】** 本工程按 TDD 执行：

1. 门禁一（`TEST_PLAN_APPROVED`）通过后**先写测试**：此时目标模块不存在，pytest 会以
   `ModuleNotFoundError` 失败——这是预期的「红」；
2. 测试写完交给用户，等待门禁二 `CONTINUE`；
3. 门禁二通过后进入 Step 4 实现，直到 `python -m pytest -q` 全绿；
4. 不允许为了让测试变绿而删改断言；golden 文件首版由人工核对后冻结，后续变更必须说明理由。

**Step 4 完成判据**：A1–A10、A13 自动化全绿 + A11/A12/A14 在 B 机逐条记录通过。

---

## 10. 明确不测的内容

| 不测 | 原因 |
|------|------|
| Qt 界面交互细节（点击、拖拽、像素布局） | 成本高收益低；v1 只做「能构造 + 能加载」的冒烟 |
| 真实游戏内注入的精确时序 | 依赖帧率与游戏实现，无法稳定自动化；由 MAN-01…MAN-07 主观验收 |
| MIDI 导出 | v1 不做（SPEC §1.2） |
| 图片/PDF 谱面识别 | M5 范围 |
| Windows 之外的平台 | 项目仅支持 Windows（SPEC §1.1） |
