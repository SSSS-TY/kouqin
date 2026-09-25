# Progress Tracker

## 仓库

- **远端**: <https://github.com/SSSS-TY/kouqin>（public，2026-09-25 建立）
- **推送用 SSH**: `ssh://git@ssh.github.com:443/SSSS-TY/kouqin.git`（与 `ssj_yq` 同一套配置）
- **分支**: `main`　**许可**: 个人非商业使用（`LICENSE`，见 ADR-004）
- git 写操作一律由用户在本地终端执行（Agent 不执行 `git init/add/commit/push`，见 ERR-001）

## Current Status

- **Active Task**: `无（v1 已结项：2026-09-25 用户回复 ARCHIVE）`
- **Task Type**: `Feature Development`
- **Last Action**: `2026-09-25 - 结项归档：README 更新为 v1 已完成、AGENTS §0 勾选完成、新增 ERR-003（焦点守卫根因）、归档任务摘要；python -m pytest -q → 164 passed，MAN-01…MAN-10 全部通过`
- **Blocked**: `否`

## 实机验收记录

| 日期 | 项目 | 结果 | 备注 |
|------|------|------|------|
| 2026-09-25 | MAN-01（小星星整曲） | ✅ 通过 | 用户反馈：旋律是小星星、无明显错音、节奏正常、长音正常。**该曲全为自然音，未覆盖鼠标修饰键路径** |
| 2026-09-25 | MAN-02（升降音/八度） | ✅ 通过 | `scores/chromatic.kq`（37 音半音阶、6 种修饰组合）：运行正常、听感无问题 |
| 2026-09-25 | P0-7（长音衰减） | ✅ 完成 | 2/4/6/8/10 秒均正常；**第 6 段（12 秒）约到 10 秒时明显衰减、很快听不见，而游戏内仍显示按键被按住** → `sustain_limit_ms = 6000` |
| 2026-09-25 | MAN-03（长音重触发） | ⏳ 待测 | 6 秒重触发已启用；普通曲子最长 2 拍不会触发，需专门的长音曲复测 |
| 2026-09-25 | MAN-04（停止/急停） | ⏳ 待测 | 命令行下可测 Ctrl+C 急停 |
| 2026-09-25 | MAN-05（未校准保护） | ✅ 通过 | 用户确认「校准约束没问题」 |
| 2026-09-25 | MAN-06（错误提示） | ✅ 通过 | 用户确认「错误提示也没问题」 |
| 2026-09-25 | 焦点守卫 | ⏳ 待测 | 新增：演奏中 Alt+Tab 离开游戏 → 立即停止并释放按键；前台是本程序时拒绝开始 |
| 2026-09-25 | 焦点守卫（基本路径） | ✅ 通过 | 用户确认「现在界面的启动也可用了」。根因是 Win32 句柄截断导致误判，已修并补测 |
| 2026-09-25 | MAN-04（停止/急停） | ✅ 通过 | 用户确认「没问题」 |
| 2026-09-25 | MAN-07（游戏内热键） | ✅ 可用 | 用户确认「可用」；**附带发现暂停变长按的缺陷 → 已修** |
| 2026-09-25 | MAN-08（焦点守卫） | ✅ 通过 | 用户确认「也没问题」 |
| 2026-09-25 | MAN-10（暂停语义） | ⏳ 待测 | 暂停＝静音已实现：松开按住的发声键、修饰键保持；恢复时按剩余时值重按 |
| 2026-09-25 | MAN-09（拒绝开始） | ✅ 通过 | 用户确认「不切回游戏不会开始」 |
| 2026-09-25 | MAN-10（暂停语义） | ✅ 通过 | 用户确认「没问题了」 |

**长音结论**：小星星的 2 拍长音（1.2 秒）正常；P0-7 实测约 10 秒起衰减。
`sustain_limit_ms` 已由 `null` 改为 **6000**（保留 4 秒余量），长音重触发随之启用。
关键观测：**衰减时游戏内仍显示按键被按住** → 音量包络与按键状态无关，只能靠「松开再按」重启声音。

## 背景（2026-09-25 用户需求）

《三角洲行动》游戏内有乐器类道具「口琴」：

- 按键 `z x c v b n m ,` 分别对应简谱 `1 2 3 4 5 6 7 1̇`
- 按住鼠标左键 = 降调，按住滚轮 = 半音，按住右键 = 升调

需求：做一个鼠标 & 键盘宏，能够照着乐谱自动演奏；并提供 UI 用于曲谱选择、导入/导出等，后续逐步完善。

## P0 实测记录（2026-09-25，游戏机 B）

用户原始反馈：

1. 注入验证完成，**能听到声音**。
2. 发现**游戏 UI 会标注音阶**：不按鼠标时 `z x c v b n m` = `1 2 3 4 5 6 7`，`,` = `1`（数字上有点，高八度）；
   按住**左键** = `1..7`（数字下有点，低八度）+ `1`（无点）；按住**中键** = `1..7` 均带 `#`（左上角）+ `#1̇`；
   按住**右键** = `1..7`（数字上有点）+ `1`（两个点）。
3. `hold-sweep`：**第 1 段（20 ms）就能听见**，之后每段声音更大、更久。
4. 追加：**按住中键再按住左键**，保持两者按住时，在左键的低音八度基础上**所有音都带 `#`**
   → 两个修饰键**效果相加**（−12 + 1 = −11）。
5. 追加：**「右键 + 中键」同样生效**（+13）。
6. 连按：**正常手速下不吞音**。
7. 长按：持续出声并**越来越大**，随后出现**「波浪感」**（疑似模拟一口气的末段），最后**变小到消失**
   → 长音必须靠**分段重触发**才能延长，不能只靠一直按住。
8. 用户决策：**曲谱导入几种方式都要支持**；全局热键**不要用 F8 / F9**。

据此得到的结论（已固化）：

| 项 | 结论 | 落位 |
|---|---|---|
| 左键 | **−12 半音**（降一个八度） | `config/instrument.json` |
| 中键 | **+1 半音**（升半音） | `config/instrument.json` |
| 右键 | **+12 半音**（升一个八度） | `config/instrument.json` |
| 注入方式 | **纯 Python `SendInput` 生效** | ADR-003（取代 ADR-001） |
| 最短可按时长 | 20 ms 可听见；实现暂取 `min_hold_ms = 40` | 设计文档 §8 P0-3 |
| 组合键 | **可叠加**（左+中 = −11：左键的低音八度全部加 `#`） | `config/instrument.json` 的 `modifier_sets` |
| 组合键 | 「右键 + 中键」也生效（+13：高音区全部加 `#`） | `config/instrument.json` |
| 音域覆盖 | **−12 … +24 共 37 个半音全覆盖**（低音 1 → 两点 1，三个八度的完整半音阶） | 设计文档 §3.2 + 配置回归测试 |
| 同音连打 | 正常手速（≈120 ms 间隔以上）**不吞音**；更快的下限未测（U11） | `config/settings.json` 的 `note_gap_ms` 说明 |
| 长音行为 | 渐强 → 波浪感 → **约 10 秒起衰减消失（按键仍按住）**；必须分段重触发 | 设计文档 §5.2 规则 5、`sustain_limit_ms: 6000` |
| 导入范围 | 文本简谱 / JSON / **MIDI** 进 v1；图片/PDF 进 M5 | 设计文档 §4.3、§10 |
| 热键 | 不用 F8/F9 → 默认 `Ctrl+Alt+P` / `Ctrl+Alt+U` / `Ctrl+Alt+K`（L 被 QQ 占用，2026-09-25 更换） | `config/settings.json`、设计文档 §7.1 |

## Next Steps

1. [x] **门禁一 `TEST_PLAN_APPROVED`** —— 用户批准（2026-09-25），并确认规格勘误 E1–E4
2. [x] **编写测试（红例）** —— 19 个样例素材 + 80 个测试函数；`python -m pytest -q` 因 `No module named 'kouqin'` 收集失败（预期红），已有 37 个测试仍全绿
3. [x] **门禁二 `CONTINUE`** —— 用户批准（2026-09-25）
4. [x] **M2 内核与曲谱** —— `kouqin/core`（score/pitch/instrument/compile）+ `kouqin/scores`（kq/json_score/midi）+ `kouqin/settings.py`；A1–A10、A13 的自动化测试全绿
5. [x] **M3 注入与播放引擎** —— `kouqin/input/win32.py`（SendInput 扫描码 + release_all）+ `kouqin/player/engine.py`（专用线程、暂停/停止/急停、循环、进度回调）；另有 CLI 作为实测通道
6. [x] **M4 界面** —— `kouqin/ui/{main_window,preview,dialogs}.py` + `kouqin/hotkey/win32.py` + `kouqin/scores/library.py`：曲谱库、编辑器与实时报错、音符预览、播放控制条、设置（播放参数/热键/键位表）、校准（试拍 + 回填）、全局热键
    - **验证**: 3 条 UI 冒烟测试通过（能加载曲谱并编译、未校准时禁用播放、错误谱面报 KQ004）；`python -m pytest -q` → 142 passed
7. [ ] **游戏内验收（用户，B 机）** —— 剩余三项：
    - MAN-03 长音（依赖 P0-7 的数值）
    - MAN-04 界面上的停止/急停（`Ctrl+Alt+K`；若也被占用，用设置页的「检测」换一个）
    - MAN-07 全局热键 `Ctrl+Alt+P` / `Ctrl+Alt+U` 在游戏内是否生效且不触发游戏动作
    - MAN-05（未校准保护）与 MAN-06（错误行标红）已由 UI 冒烟测试覆盖代码路径，仍建议在 B 机目视确认一次
8. [x] **P0-7 长音衰减计时** —— 实测约 10 秒起衰减 → `sustain_limit_ms = 6000`（2026-09-25）
9. [ ] **（可选）界面便携化** —— 若 B 机不方便装 PySide6，评估用便携包随附（待用户决定）

## Suspended Tasks

（暂无）

## Blockers

- [ ] 等待门禁二 `CONTINUE`
  - **需要**: 用户在测试就绪（红例）后回复 `CONTINUE`；另需知晓测试期新增的两条规范补充 E5（负时间平移）/E6（换修饰时序模型）
  - **关联错误**: 无（ERR-001/ERR-002 均已 Resolved）

## Completed

- ✅ [2026-09-25] 工程初始化：创建 `AGENTS.md`（基于通用模板实例化）、`README.md`、`.gitignore`、`docs/harness/*`、`docs/design/DESIGN_SUMMARY_FOR_OPENSPEC.md`
  - **验证**: 逐个 `Test-Path` 确认文件存在（见本任务最终汇报）
  - **Commit**: `未提交（用户本地执行）`
- ✅ [2026-09-25] 环境事故处理：沙盒内 `git init` 导致命令工具全面失效；已删除该空仓库恢复环境，并记录 `docs/harness/errors/ERR-001.md`，规则写入 `AGENTS.md` §4.3/§8.3
  - **验证**: `Test-Path D:\codex\kouqin\.git` → `False`；恢复后普通命令正常执行
  - **Commit**: `未提交（用户本地执行）`
- ✅ [2026-09-25] P0 注入实验工具 `tools/p0_sendinput_demo.py`：纯 ctypes SendInput（扫描码），含 `check` / `scale` / `key` / `hold-sweep` / `compare` / `mouse` 六个模式，支持 `--dry-run`，退出时释放全部按住的键
  - **验证**: `python -m pytest -q` → 16 passed；`check` 与各模式 `--dry-run` 实跑通过
  - **Commit**: `未提交（用户本地执行）`
- ✅ [2026-09-25] B 机拷贝方案：`docs/RUN_ON_B.md`（拷贝清单、B 机前提、操作顺序、回传项）+ `tools/make_bundle.py`（打包到 `%TEMP%\kouqin_bundle`，可 `--zip`）
  - **验证**: `python -m pytest -q` → 22 passed；实跑打包 → 4 文件 30.3 KB / zip 12.2 KB；把 demo 单独拷到空目录后 `--dry-run` 仍可运行（单文件自包含成立）
  - **Commit**: `未提交（用户本地执行）`
- ✅ [2026-09-25] **P0 实测完成**（用户在游戏机 B）：注入生效、修饰键音程、最短可按时长全部关闭；原始反馈见上文「P0 实测记录」
  - **验证**: 用户确认 `scale` 听到 8 音上行；游戏内标注给出键位→音高映射；`hold-sweep` 第 1 段（20 ms）即可听见
  - **Commit**: `未提交（用户本地执行）`
- ✅ [2026-09-25] 校准结果落盘为 `config/instrument.json`（`verified: true`）+ 新增 `tests/unit/test_instrument_config.py`（键位/半音数/音域覆盖/低音区变化音不可达）
  - **验证**: `python -m pytest -q` → 28 passed
  - **Commit**: `未提交（用户本地执行）`
- ✅ [2026-09-25] 决策与设计修订：新增 ADR-003（纯 Python 单进程，取代 ADR-001），设计文档 §2 实测结论、§3.2 音域覆盖、§5.4 取消 IPC 契约、§6 单进程架构、§8 P0 结果全部同步
  - **验证**: 文档内引用与 `config/instrument.json`、ADR-003 结论一致
  - **Commit**: `未提交（用户本地执行）`
- ✅ [2026-09-25] 第二轮实测落盘：右键+中键通过（音域扩到 **−12…+24 共 37 个半音**）、正常手速连按不吞音、长按呈「渐强→波浪感→消失」包络
  - **修改**: `config/instrument.json`（组合全部 verified）、新增 `config/settings.json`（播放参数 + 每项依据 + 热键）、新增 `tests/unit/test_settings_config.py`
  - **验证**: `python -m pytest -q` → 34 passed（含"不得存在未实测组合""sustain_limit_ms 未测必须为 null""热键不得用 F8/F9"等断言）
  - **Commit**: `未提交（用户本地执行）`
- ✅ [2026-09-25] 用户决策落盘：导入方式**全支持**（v1 含 MIDI，用纯标准库解析 SMF，不新增依赖；图片/PDF 进 M5）；热键**不用 F8/F9**，改为 `Ctrl+Alt+P/U/L`
  - **落位**: 设计文档 §4.3、§7.1、§9、§10、§11；`config/settings.json`
  - **验证**: 文档与配置一致；`test_hotkeys_avoid_f8_and_f9` 通过
  - **Commit**: `未提交（用户本地执行）`
- ✅ [2026-09-25] 版本控制准备：确认 git 身份**未设置过**（`~/.gitconfig` 仅 `[safe] directory = *`；`ssj_yq` 的身份是仓库级 local）；新增 `.gitattributes` 锁定 LF（系统级 `core.autocrlf=true` 会在检出时改成 CRLF）
  - **验证**: `git config --show-origin --get-all user.name` 为空；21 个文件当前全部为 LF
  - **Commit**: `未提交（用户本地执行）`
- ✅ [2026-09-25] 许可与公开策略：新增 `LICENSE`（个人非商业使用许可 v1.0）+ `README.md` 许可小节 + ADR-004（public 仓库、仅 owner 可推送、禁止再分发与商业用途）
  - **验证**: 发布前敏感信息扫描无命中（无密钥/邮箱写入文件）；文档与许可条款一致
  - **Commit**: `未提交（用户本地执行）`
- ✅ [2026-09-25] 远端仓库建立并完成首次推送（<https://github.com/SSSS-TY/kouqin>，public）；期间因 GitHub 邮箱隐私保护触发 GH007，已按 `ERR-002` 修复（noreply 邮箱 + 重写提交 + 强推）
  - **验证**: 推送成功（45 对象 / 63.38 KiB，`+ 99fa4ce...a116d67 main -> main (forced update)`）；`git log` 三个提交作者均为 `332089221+SSSS-TY@users.noreply.github.com`
  - **Commit**: `a116d67`
- ✅ [2026-09-25] **设计门禁通过（用户回复 `APPROVED`）**：ADR-002 / ADR-003 转为 `Accepted`；热键方案（`Ctrl+Alt+P/U/L`）经用户确认可用
  - **验证**: 用户消息原文「APPROVED，你前面提到的新热键应该可用」
  - **Commit**: `未提交（用户本地执行）`
- ✅ [2026-09-25] **Step 2 规格产出**：`docs/design/SPEC.md` v1.0（数据契约、模块接口、编译算法、线程与热键模型、UI 规格、错误码表、14 条可测验收标准、4 条未决项）
  - **配套改动**: `config/settings.json` 新增 `midi` 区块（MIDI 60 → s=0）与对应依据说明；`tests/unit/test_settings_config.py` 增加 MIDI 参考音与说明覆盖断言
  - **验证**: `python -m pytest -q` → 37 passed
  - **Commit**: `未提交（用户本地执行）`
- ✅ [2026-09-25] P0-7 测量工具：实验工具新增 `sustain` 模式（依次按住 2/4/6/8/10/12 秒，2 秒间隔），并补充两项单元测试
  - **验证**: `python -m pytest -q` → 37 passed；`sustain --dry-run` 实跑输出 12 个事件
  - **Commit**: `未提交（用户本地执行）`
- ✅ [2026-09-25] **规格门禁通过（用户回复 `SPEC_APPROVED`）**
  - **产出**: `docs/design/SPEC.md` v1.0（293 行，规范性：数据契约 / 模块接口 / 编译算法 / 线程与热键模型 / UI 规格 / 20 个错误码 / A1–A14 验收标准 / 4 条未决项）
  - **Commit**: `未提交（用户本地执行）`
- ✅ [2026-09-25] **Step 3 测试计划产出**：`docs/design/TEST_PLAN.md` v1.0（284 行）
  - **内容**: 87 个用例（P11 / K22 / J3 / M10 / C14 / E9 / G7 / R4 / MAN7）+ 覆盖矩阵 + 层级与素材清单 + 红例策略 + 不测范围
  - **同时提出 4 条规格勘误 E1–E4**（`hold_ms` 上界、长音切分预算、休止跨越、KQ006 死码），待用户与门禁一并确认
  - **验证**: 用例 ID 与 A1–A14 的覆盖矩阵完整（无遗漏验收标准）；`python -m pytest -q` → 37 passed（现有测试未受影响）
  - **Commit**: `未提交（用户本地执行）`
- ✅ [2026-09-25] **测试计划门禁通过（用户回复 `TEST_PLAN_APPROVED` + 同意 E1–E4）**；E1–E4 已并入 `SPEC.md`（记为 v1.1 勘误，不新开 ADR）
  - **验证**: 用户消息原文「E1–E4 是否同意，TEST_PLAN_APPROVED」
  - **Commit**: `未提交（用户本地执行）`
- ✅ [2026-09-25] **Step 3 测试编写完成（红例阶段）**
  - **素材**: 11 个 `.kq` 样例、7 个 `.mid` 二进制（由 `tools/make_test_midi.py` 确定性生成）、1 个 golden 计划 `expected/golden_bar.plan.json`（手工推导）
  - **测试**: 8 个新测试文件、80 个测试函数（`test_pitch_mapping`/`test_kq_parser`/`test_score_json`/`test_midi_import`/`test_compile_plan`/`test_player_engine`/`test_contracts`/`test_invariants`）+ `tests/manual/ACCEPTANCE.md`
  - **测试期新增两条规范补充**：E5（负时间整体平移 + `offset_ms`）、E6（换修饰时序模型 = 相同组合不重按；最小间隔 `lead+tail`）；已并入 SPEC §5.4 与 §13，并在 TEST_PLAN §11 列出实现必须满足的接口细节（T1–T13、S1–S3）
  - **验证**: `python -m pytest -q` → 8 个文件以 `ModuleNotFoundError: No module named 'kouqin'` 收集失败（**预期的红**）；`python -m pytest -q tests/unit/test_{instrument_config,settings_config,p0_sendinput_demo,make_bundle}.py` → **37 passed**（既有测试未受影响）
  - **Commit**: `未提交（用户本地执行）`
- ✅ [2026-09-25] **门禁二 `CONTINUE`**（用户批准）
- ✅ [2026-09-25] **M2 内核与曲谱实现**：`kouqin/core/{score,pitch,instrument,compile}.py`、`kouqin/scores/{kq,json_score,midi}.py`、`kouqin/settings.py`
  - 编译实现含勘误 E1–E7；额外发现并修复「逐音独立取整导致 1 ms 重叠」（改为强制首尾相接）
  - **验证**: A1–A10、A13 的用例全绿（含 golden 计划逐事件比对、MIDI 三轨合并/打击轨忽略/和弦丢弃、随机不变量 5×40 首）
- ✅ [2026-09-25] **M3 注入与播放引擎实现**：`kouqin/input/win32.py`（扫描码 SendInput + `release_all` + 权限自检）、`kouqin/player/engine.py`（专用线程、2 ms 轮询响应暂停/停止/急停、循环、进度回调、异常路径强制释放）
  - **验证**: E-01…E-09 全绿（含急停 ≤100 ms、注入异常后状态为 error 且已释放、暂停期间零事件）
- ✅ [2026-09-25] **CLI 实测通道**：`python -m kouqin {dry-run,play,check}` + 首支曲谱 `scores/twinkle.kq`（小星星）
  - **验证**: `check` 正常输出；`dry-run scores\twinkle.kq` → 42 音 / 84 事件 / 28.77 秒；`dry-run tests\fixtures\midi\sample_multi.mid` 正常；错误路径 `bad_tie.kq` → 退出码 2 + KQ008 提示
  - **全量验证**: `python -m pytest -q` → **138 passed**（连续两次，无抖动）；`python -m compileall -q kouqin tools tests` → 0
- ✅ [2026-09-25] **B 机拷贝清单随实现更新**：`tools/make_bundle.py` 改为「目录级拷贝」（整个 `kouqin` 包 + `config` + `scores` + LICENSE + P0 工具），新增 `--with-tests`
  - **产物**: 24 个文件 / 94.4 KB；`--zip` → 42.7 KB
  - **独立性验证**: 拷到独立目录后用 `python -S`（关闭 site-packages）运行 `python -m kouqin dry-run scores\twinkle.kq` 成功 → 证明**无任何第三方依赖**；从子目录运行亦正常（CLI 增加了配置路径回退）
  - **文档**: `docs/RUN_ON_B.md` 重写（不再需要 AutoHotkey / PySide6；列出新拷贝清单与 `check`→`dry-run`→`play` 步骤）
  - **验证**: `python -m pytest -q tests/unit/test_make_bundle.py` → 7 passed
- ✅ [2026-09-25] **MAN-02 实机通过**（用户，B 机）：`scores/chromatic.kq`（37 音半音阶）运行正常、听感无问题
  - **含义**: 至此「解析 → 音高映射（含 6 种修饰组合）→ 编译 → SendInput 注入 → 游戏发声」全链路在真实游戏里验证通过
- ✅ [2026-09-25] **M4 图形界面完成**：`kouqin/ui/main_window.py`（三区布局、菜单、播放控制、进度、状态栏）、`preview.py`（音符条形图 + 不可达标红 + 当前音高亮）、`dialogs.py`（设置：播放参数/热键/键位表；校准：逐组合试拍 + 回填半音数 + 写入 verified）、`kouqin/hotkey/win32.py`（RegisterHotKey + WM_HOTKEY 原生事件过滤）、`kouqin/scores/library.py`（曲谱库扫描与可达性标记）
  - **修复**: UI 冒烟测试抓出「构造函数里只启动防抖定时器、未同步解析」导致按钮状态陈旧的 bug → 显式操作改为立即解析
  - **验证**: `python -m pytest -q` → **142 passed**（新增 3 条 UI 冒烟测试）；`python -m compileall -q kouqin tools tests` → 0；打包后 `kouqin` 包 24 个文件全部随行（zip 58.1 KB）
- ✅ [2026-09-25] **热键冲突处理（用户发现 `Ctrl+Alt+L` 被 QQ 占用）**
  - 默认急停键 `Ctrl+Alt+L` → **`Ctrl+Alt+K`**（`config/settings.json` 与 `kouqin/settings.py` 同步；文档 6 处引用一并更新）
  - 新增 `probe(hwnd, combo) -> (bool, str)`：试注册即注销，能区分「已被其它程序占用」（Windows 1409）与「本环境无法注册」；设置页每个热键旁加「检测」按钮当场验证
  - `register()` 增加**线程消息队列回退**：窗口句柄不可用时改用当前线程队列（Qt 以 `windows_dispatcher_MSG` 交给原生事件过滤器），提高在不同环境下的可用性
  - 注册失败不再只是 10 秒状态栏提示：改为状态栏 20 秒提示 + 一次性弹窗，明确指向设置页
  - **验证**: `python -m pytest -q` → **152 passed**（新增 9 条热键解析/默认值测试）；占用检测自检：先占住 `Ctrl+Alt+K` → `(False, '已被其它程序占用')`，释放后 → `(True, '可用')`

## 第二轮用户反馈与处理（2026-09-25）

用户反馈 5 条，其中 2 条是设计缺陷：

| # | 反馈 | 处理 |
|---|------|------|
| 1 | 热键「检测」**全部显示被占用**，但 P/U 实际可用 | **Agent 的 bug**：本程序已注册这三个键，重复试注册命中 Windows 1409 被误判为「被别的程序占用」。修复：`HotkeyManager.probe()` 先临时注销自己的注册、探测后原样恢复 |
| 2 | 界面优化等基本功能稳定后再做 | 记录，暂不动 UI 视觉与交互 |
| 3 | **设计矛盾**：游戏内点不到 UI；切出程序后宏仍在向新前台窗口发按键（会在别的程序里乱打字） | 新增**焦点守卫**（`pause_when_unfocused`，默认开）：开始前记录目标窗口并拒绝「前台是本程序」的情况；演奏中每 ≤50 ms 复查，焦点离开 → 立即释放全部按键并停止（新状态 `unfocused`） |
| 4 | 校准约束、MAN-06 错误提示都没问题 | 记入验收记录（MAN-05 / MAN-06 ✅） |
| 5 | 长音**重触发的接缝较明显** | `sustain_limit_ms` 6 s → **8 s**（离实测衰减点 10 s 留 2 s 余量，普通曲子更不会触发）；新增 `retrigger_gap_ms = 12`（原用 `note_gap_ms = 30`），缩短「松开再按」的间隔以减小接缝 |

- **验证**: `python -m pytest -q` → **155 passed**（新增 E-10「前台是本程序时拒绝开始且不发任何按键」、E-11「焦点离开后立即释放并置 `unfocused`」、热键探测解除自身占用 3 条）
- **行为核对**: `dry-run scores\long_note.kq` → 12 秒长音在 9979/9991 ms 处重触发（段间 12 ms，总跨度不变）

### 焦点守卫回归（用户报「现在无法播放了」）

- **现象**: 加了焦点守卫后，点开始没有任何反应。
- **根因**: `FocusGuard.ok()` 在**尚未锁定目标窗口**（倒计时阶段）时返回 `False`
  （因为 `target == 0`），于是倒计时一开始就被判成「焦点离开」并中止。
  实现时只顾了「播放期间要盯住目标窗口」，忘了守卫在锁定之前必须保持中立。
- **修复**: `ok()` 在 `target == 0` 时**一律返回 True（不拦截）**；同时把 `capture()` 的返回值从
  `bool` 改成 `str | None`（失败时给出具体原因），并新增拒绝终端窗口
  （把 `z x c v` 打进终端只会得到乱码）。
- **补齐测试**（这次漏测是根因）:
  - `tests/unit/test_focus_guard.py`：5 条纯逻辑用例，第一条专门守住「未锁定时不得拦截」；
  - `E-12`：**真实 FocusGuard + 倒计时**跑完整首短曲（Win32 调用用替身），
    直接复现用户场景——这条如果早写，就不会漏。
- **结果**: `python -m pytest -q` → **161 passed**

### 焦点守卫第二次故障与根本修复（2026-09-25）

- **现象**: 在窗口里点「开始」仍报「焦点离开了目标窗口，已停止演奏并释放所有按键」（用户第 1 条反馈）。
- **根因（已定位）**: `GetForegroundWindow` / `GetWindowThreadProcessId` 等 Win32 函数**没有声明 ctypes 签名**，
  64 位下 `restype` 默认按 32 位 int 处理 → 句柄被截断 → `window_pid()` 取不到进程号返回 0 →
  「前台是本程序」这条检查失效 → **守卫把本程序自己的窗口当成了目标窗口**；
  用户随后切回游戏，前台变化 → 立刻报「焦点离开」。
- **修复**:
  1. 为 `GetForegroundWindow` / `GetWindowThreadProcessId` / `GetWindowTextW` / `GetClassNameW`
     显式声明 argtypes/restype；
  2. `window_pid()` 取不到进程号（0）时**宁可拒绝**，不再默默当成合法目标；
  3. 新增**焦点宽限**（`focus_grace_s`，默认 1.2 秒）：Alt+Tab 过程中焦点抖动，只要在宽限期内切回来就继续演奏
     （并把等待时间补回时钟，不跳拍）；
  4. 停止时的提示带上「目标窗口 vs 当前前台」标题，便于定位是谁抢走了焦点；
  5. `check` 命令新增前台窗口标题 / 窗口类 / 归属进程输出。
- **补齐测试**: `FocusGuard` 用例增至 6 条（含「取不到进程号必须拒绝」）；`E-13` 覆盖宽限期内切回来不中止。

### 长音重触发裁决（用户第 3 条反馈）

- 用户反馈 `long_note.kq` 的接缝**仍然明显**，建议放弃断点重按。
- **裁决**：`retrigger_long_notes` **默认改为 false**（接受约 10 秒后的自然衰减）；
  能力保留为可选开关，`sustain_limit_ms = 8000` 与 `retrigger_gap_ms = 12` 仍记录在案。
- 相应更新：`config/settings.json`、`kouqin/settings.py`、测试固定参数、golden 计划；
  C-04 与 R-02 改为显式打开重触发来继续覆盖「切分」这条能力。
- **结果**: `python -m pytest -q` → **163 passed**

### 暂停变「长按」缺陷（MAN-07 附带发现，2026-09-25）

- **现象**: 在某个音**按住期间**按 `Ctrl+Alt+U` 暂停，游戏里那个音一直在响（表现为长按）。
- **根因**: 暂停的实现只是「冻住时钟」，没有松开已按下的键——按住的键当然会一直发声。
  这正是「暂停」与「静音」的语义差别，之前没写清楚。
- **修复**: 暂停 = **静音**：
  - Player 线程进入暂停等待**之前**，松开当前所有**发声键**；
  - **鼠标修饰键保持按住**（避免恢复时音高先于修饰键生效，导致那个音的音高错）；
  - 恢复时按**剩余时值**重新按下这些键（时钟在暂停期间冻结，剩余时值不变）。
  - 代价：恢复瞬间有一次重新起音——暂停是用户显式操作，可以接受。
- **规范**: 写入 `SPEC.md` §6.2「暂停语义」（【规范性】）。
- **测试**: 更新 E-05（暂停期间不得再发事件，允许那一次松开）；新增 E-14（暂停必须松开按键且
  `is_everything_released()`、恢复必须重按）。`python -m pytest -q` → **164 passed**

## Archive

- 2026-W39: **v1 完成（口琴自动演奏宏）**
  - **交付**: 单进程 Python 应用（PySide6 界面 + 后台播放线程 + ctypes SendInput 注入），含曲谱解析（`.kq`/`.kq.json`/MIDI）、演奏计划编译、播放控制（开始/暂停/停止/急停/循环/速度/移调）、焦点守卫、全局热键、曲谱库与校准界面、命令行通道。
  - **验收**: 自动化 164 项全绿；游戏内 MAN-01…MAN-10 全部通过（小星星整曲、37 音半音阶覆盖 6 种修饰组合、长音裁决、停止/急停、游戏内热键、焦点守卫、拒绝开始、暂停＝静音）。
  - **关键难点**:
    1. 乐器语义靠**游戏内音阶标注**一次性读全（左 −12 / 中 +1 / 右 +12，且可叠加），音域覆盖 37 个半音；
    2. 编译期的边界规则（`hold_ms` 上界、长音切分预算、休止跨越、KQ006 死码、负时间平移、换修饰时序）共 7 条勘误，全部由测试暴露并写回 SPEC；
    3. **焦点守卫连续两次误判**：先是「未锁定就拦截」，再是「Win32 缺 ctypes 签名导致句柄截断」——见 ERR-003；
    4. 长音重触发经实测后**被否决**（接缝必然可闻），默认关闭、能力保留（ADR-006）。
  - **剩余风险**: 超过约 10 秒的长音会自然衰减（游戏本身的呼吸包络）；B 机用界面需装 PySide6；界面视觉优化与 U5/U11 测量留待后续。
