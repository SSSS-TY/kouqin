# Architecture Decisions

> 按 `AGENTS.md` §11 追加决策记录。技术选型类 ADR 在 Step 1 设计阶段以 `Proposed` 落盘，
> 用户回复 `APPROVED` 后转为 `Accepted`。

## ADR-001: 双进程架构 —— PySide6 界面 + AutoHotkey v2 运行时

- **Date**: 2026-09-25
- **Status**: Superseded
- **Supersedes**: N/A
- **Superseded by**: ADR-003（2026-09-25：P0-2 实测证明纯 Python 注入可用，不再需要第二个进程）

### Context

- 需求同时包含两件性质不同的工作：①「照着乐谱演奏」所需的**精确、可重复的时序输入注入**；
  ② 曲谱库、导入/导出、编辑与校准所需的**图形界面**。
- 同目录的在建工程 `ssj_yq`（同为《三角洲行动》）已在同一个游戏上验证过 **AHK v2 + 高精度计时
  （QueryPerformanceCounter）+ JSON 配置**的输入注入链路可用；该工程未验证过非 AHK 的注入方案。
- 本机已安装 AutoHotkey v2.0.23 与 PySide6 6.11.1，两者均无需新增依赖。

### Decision

1. **界面与领域逻辑用 Python**：PySide6 负责界面；`kouqin/core` 与 `kouqin/scores` 作为纯逻辑层（可单测、无 Qt 依赖）。
2. **输入注入只在 AHK v2 运行时发生**：`macro/kouqin_runtime.ahk` 负责播放计划的时序执行与键盘/鼠标注入。
3. **两个进程通过 JSON 契约文件通信**：Python 侧写出 `runtime/plan.json`（演奏计划）与
   `runtime/control.json`（命令），AHK 轮询命令并回写 `runtime/state.json`（状态与进度）。
4. AHK 运行时复用 `ssj_yq` 已验证的计时做法（QPC + 高精度等待），不引入第三方 AHK 库。

### Consequences

#### Positive

- 复用同游戏中已被验证的注入链路，风险与工作量可控。
- 内核逻辑与界面解耦，曲谱解析/编译/音高映射可完全离线单测。
- 契约文件可读，可作为 dry-run 的核对产物（先核对事件序列，再进游戏）。

#### Negative

- 双进程带来 IPC 复杂度：启动/停止/暂停的生效延迟受轮询周期限制（设计目标 ≤ 100ms）。
- 运行时契约（JSON 字段）变更必须两侧同步，否则静默失效（已写入 `AGENTS.md` §5.4）。
- AHK 侧代码可测试性弱于 Python 侧，只能依赖 dry-run 与游戏内手动验收。

### Alternatives Considered

- **纯 Python 注入（ctypes SendInput）**：单进程、易测试、延迟更低，但在该游戏上**未被验证**；
  若 AHK 路线在 P0-2 中失败，或用户希望简化部署，再评估（需新 ADR）。
- **纯 AHK 实现（含界面）**：AHK 做界面不利于曲谱库与文本处理，且测试能力弱；不采用。
- **每次播放重启 AHK 进程**：启动延迟与热键状态管理更差；不采用。

### Verification

- P0-2 实验确认 AHK 注入在游戏内生效且最短可靠按键时长可控；
- P0-2 同时用 `tools/p0_sendinput_demo.py` 测 Python SendInput：若 Python 也生效，重新评估本 ADR 的运行时路线；
- 手动验收：游戏内播放一首含升降音与休止的曲目，音高与时值主观正确；
- 停止按钮在 ≤100ms 内生效，且停止后不留任何按下的键/鼠标键。

## ADR-002: 曲谱双格式（文本简谱 DSL + JSON），内部统一为绝对拍位

- **Date**: 2026-09-25
- **Status**: Accepted（2026-09-25 随设计门禁 `APPROVED` 一并确认）
- **Supersedes**: N/A
- **Superseded by**: N/A

### Context

- 用户的核心诉求是「照着乐谱演奏」，乐谱可能来自手敲、粘贴或后续的文件导入。
- 口琴是**单音**乐器：同一时刻只有一个音高在响，不存在和弦需求。
- 曲谱需要人类可读（便于手改、分享、审阅），也需要机器精确（便于保存与无损往返）。

### Decision

1. **文本简谱 DSL（`.kq`）作为主要创作格式**：一行行简谱（例 `1 1 5 5 | 6 6 5-`），带 `@title` / `@tempo` 等元信息。
2. **JSON（`.kq.json`）作为精确存储与交换格式**：保存每音的起始拍与拍数，供导入导出与无损往返。
3. **内部统一表示**：解析后一律转成「相对拍」的音符列表（`start_beat` / `duration_beat` / `pitch`），
   编译阶段再按 BPM 换算为绝对毫秒事件序列。
4. 不支持和弦、多声部；不支持连音线以外的复杂记谱（延音用 `-`，断音由编译期的最小间隔参数控制）。

### Consequences

#### Positive

- 文本格式便于用户手工编写与版本管理，JSON 保证精确往返。
- 内部单一表示避免了「两套时间语义」的长期隐患。

#### Negative

- 需要维护两套读写器与它们的等价性测试（`.kq` ↔ `.kq.json` 往返一致）。
- 复杂乐谱（转调、复杂节奏）表达力有限；超出时需扩展 DSL（走完整四步法）。

### Alternatives Considered

- **仅 JSON**：不利于手写与审阅；不采用。
- **仅文本 DSL**：浮点节奏与精度易受格式影响；不采用。
- **MIDI 作为主要格式**：表达力强但引入新依赖（`mido`）且对简谱不直观；列为后续可选导入源。

### Verification

- 往返测试：`.kq` → 内部表示 → `.kq.json` → 内部表示，两次结果逐音相等；
- 编译测试：给定 BPM 与拍号，事件时间与预期毫秒严格一致。

## ADR-003: 改用纯 Python 单进程（取代 ADR-001 的双进程运行时）

- **Date**: 2026-09-25
- **Status**: Accepted（2026-09-25 用户在设计门禁回复 `APPROVED`）
- **Supersedes**: ADR-001
- **Superseded by**: N/A

### Context

- ADR-001 选择「PySide6 界面 + AHK v2 运行时 + JSON 契约文件」，理由是 AHK 注入在 `ssj_yq` 中已验证，
  而 Python 注入在当时**尚未验证**。
- 2026-09-25 用户要求先试纯 Python 注入，据此新增实验工具 `tools/p0_sendinput_demo.py`。
- **实测结论（P0-2）**：用 ctypes `SendInput`（`KEYEVENTF_SCANCODE` 扫描码）在游戏内成功触发完整音阶，
  用户听到 `z x c v b n m ,` 的 8 音上行；P0-1、P0-3 亦由同一工具与游戏内音阶标注完成。
- 实际部署目标是另一台**游戏机 B**，依赖越少越好；B 上本来就需要 Python（曲谱处理与界面），
  若同时保留 AHK 则需额外安装或携带解释器。

### Decision

1. **取消 AHK 运行时**：播放引擎、时序与输入注入都在同一个 Python 进程内完成。
2. **取消 `runtime/control.json` / `runtime/state.json` 这对 IPC 契约**：播放控制与进度改为进程内队列与回调。
3. `runtime/plan.json` 保留，但**降级为 dry-run 调试产物**（离线核对与排障用），不再是进程间通道。
4. 注入实现沿用实验工具中已验证的做法：扫描码键盘事件 + 鼠标键事件；
   时序用 `perf_counter` 绝对时刻 + `sleep`/忙等混合（最后 2 ms 忙等）。
5. **AHK 路线保留为备选**：若将来 Python 注入失效（游戏更新、权限模型变化），再回到 ADR-001 的方案。

### Consequences

#### Positive

- 少一个进程、少一套 IPC 契约；部署到 B 机只需 Python，不需要 AutoHotkey。
- 播放逻辑与界面同进程：暂停/继续/停止更简单，生效延迟更低。
- 注入与时序逻辑可用 pytest 覆盖（事件计划、按键跟踪已单测），不依赖 AHK 侧的手动验证。

#### Negative

- 全局热键需要自己实现：ctypes `RegisterHotKey` + Qt 原生事件过滤接收 `WM_HOTKEY`（细节待 Step 2 规格固化）。
- 界面线程与播放线程必须严格解耦（进度只能经信号/队列回主线程），否则可能卡顿或竞态。
- 失去 AHK 的「轻量脚本」特性：注入行为的任何变更都要走 Python 代码与测试。

### Alternatives Considered

- **维持 ADR-001 的双进程**：在已验证存在更简单可行的方案后不再合理；仅作为备选保留。
- **Python 注入 + AHK 只做热键**：混合方案的契约与部署成本高于收益；不采用。

### Verification

- `python -m pytest -q`：注入事件计划、按键跟踪与配置回归测试全绿（28 passed）。
- 游戏内（2026-09-25，用户确认）：`python tools/p0_sendinput_demo.py scale` 触发完整 8 音上行；
  `hold-sweep` 中 20 ms 档即可听见。
- Step 4 完成后追加：游戏内播放一首含升降音、休止与长音的曲目；停止后不留按下的键。

## ADR-004: 采用「个人非商业使用」许可，仓库公开但限制再分发与商业用途

- **Date**: 2026-09-25
- **Status**: Accepted（用户 2026-09-25 明确要求）
- **Supersedes**: N/A
- **Superseded by**: N/A

### Context

- 用户决定把本仓库建为 **public**（所有人可读），但要求**只有自己可以提交**，
  且明确要求许可"仅限个人非商业使用"。
- GitHub 的权限模型天然满足"公开可读 / 仅 owner 与 collaborator 可推送"，无需额外配置。
- 本工程是游戏内乐器演奏工具。若不声明许可，默认是"保留所有权利"（他人不得合法复用），
  但意图不明确、易被误解为可自由分发。

### Decision

1. 仓库设为 **public**；推送权限仅限版权持有人（GitHub 默认行为）。
2. 新增 `LICENSE`：**个人非商业使用许可 v1.0**（中文为准，附英文摘要），
   授予个人非商业目的的运行与修改权，**禁止再分发与任何商业用途**，
   并要求不得用于自动化对战、代练、刷取资源或账号交易。
3. 明确声明本协议**不是** OSI 开源许可，属"源码可见"授权；
   同时声明本项目与游戏开发商/发行商无关联、未获其授权。
4. `README.md` 增加「许可」小节指向 `LICENSE`。

### Consequences

#### Positive

- 使用范围与用户意图一致，公开后仍能约束再分发与商业使用。
- 明确了"不用于对战自动化"的立场，降低被误认为作弊工具的歧义。

#### Negative

- 自定义许可不具备 OSI 认可地位，GitHub 无法自动识别；跨法域效力弱于成熟许可文本
  （若将来需要更强执行力，可换 PolyForm Noncommercial 等现成文本）。
- 公开仓库意味着提交作者邮箱对所有人可见，且他人可 fork（fork 后不受本许可约束，只能事后追责）。
- 公开自动化工具可能引起游戏厂商/反作弊注意。

### Alternatives Considered

- **不加许可（默认保留所有权利）**：意图不明确；不采用。
- **PolyForm Noncommercial 1.0.0**：律师起草、文本成熟，但允许"任何非商业用途"（含非个人主体）
  且允许非商业再分发，与用户"仅限个人、禁止再分发"的要求不符；列为备选（需联网获取正式文本）。
- **MIT / Apache-2.0 等开源许可**：允许商业使用与再分发；与用户要求相反，不采用。

### Verification

- `LICENSE` 与 `README.md` 的「许可」小节同时存在于仓库根与文档；
- 仓库为 public 且 `git remote -v` 仅指向用户自己的仓库；协作者列表为空。
