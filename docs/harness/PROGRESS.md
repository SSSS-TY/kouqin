# Progress Tracker

## 仓库

- **远端**: <https://github.com/SSSS-TY/kouqin>（public，2026-09-25 建立）
- **推送用 SSH**: `ssh://git@ssh.github.com:443/SSSS-TY/kouqin.git`（与 `ssj_yq` 同一套配置）
- **分支**: `main`　**许可**: 个人非商业使用（`LICENSE`，见 ADR-004）
- git 写操作一律由用户在本地终端执行（Agent 不执行 `git init/add/commit/push`，见 ERR-001）

## Current Status

- **Active Task**: `口琴自动演奏宏 v1 —— Step 1 设计（P0 关键实验已完成，设计文档已按实测修订，等待 APPROVED）`
- **Task Type**: `Feature Development`
- **Last Action**: `2026-09-25 - P0-1/P0-2/P0-3 实测完成：写入 config/instrument.json（verified=true）、新增 ADR-003（纯 Python 单进程）、设计文档 §2/§3/§5.4/§6/§8 同步修订`
- **Blocked**: `是：等待设计门禁 APPROVED（P0 关键实验已关闭；U4/U6 为可选补测）`

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
| 长音行为 | 渐强 → 波浪感 → 衰减消失；**必须分段重触发**（时间常数待测 U6 / P0-7） | 设计文档 §5.2 规则 5、`sustain_limit_ms: null` |
| 导入范围 | 文本简谱 / JSON / **MIDI** 进 v1；图片/PDF 进 M5 | 设计文档 §4.3、§10 |
| 热键 | 不用 F8/F9 → 默认 `Ctrl+Alt+P` / `Ctrl+Alt+U` / `Ctrl+Alt+L` | `config/settings.json`、设计文档 §7.1 |

## Next Steps

1. [ ] **P0-7 长音衰减计时**（用户，B 机）—— 按住一个键，报「大约几秒开始明显变弱 / 几秒完全听不见」；据此填写 `sustain_limit_ms` - `est: 3m`
2. [ ] **确认全局热键**（用户）—— `Ctrl+Alt+P`（开始/停止）、`Ctrl+Alt+U`（暂停/继续）、`Ctrl+Alt+L`（急停）是否可用 - `est: 1m`
3. [ ] **确认首次推送** —— 远端 <https://github.com/SSSS-TY/kouqin> 已建立；确认 `git status --short` 干净、`git log --oneline -1` 有首个提交（若报错请把输出发回） - `est: 1m`
4. [ ] **设计门禁** —— 用户回复 `APPROVED`（含确认 ADR-003 单进程路线与 Q4 移调/循环） - `est: 用户侧`
5. [ ] Step 2 规格 —— 产出 `docs/design/SPEC.md`（曲谱 DSL、MIDI 导入、计划契约、UI 交互、热键与线程模型、验收标准） - `est: 1.5h` - `verify: 用户回复 SPEC_APPROVED`
6. [ ] Step 3 测试计划 —— 产出 `docs/design/TEST_PLAN.md` - `est: 40m` - `verify: 用户回复 TEST_PLAN_APPROVED`
7. [ ] Step 4 实现 —— 按里程碑 M2 → M4 实现（内核/曲谱/MIDI → 注入与播放引擎 → 界面） - `est: 待评估`

## Suspended Tasks

（暂无）

## Blockers

- [ ] 等待设计门禁与乐器行为实测结论
  - **需要**: 用户回复 `APPROVED`（P0-1/P0-2/P0-3 已关闭；U4/U6 为可选补测）
  - **关联错误**: 无

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

## Archive

（暂无）
