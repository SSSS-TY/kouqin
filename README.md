# kouqin — 《三角洲行动》口琴自动演奏宏

按乐谱在游戏内自动演奏口琴道具的桌面工具：**单进程 Python 应用** —— PySide6 图形界面（曲谱库、导入/导出、播放控制、
键位校准）+ 后台播放线程（精确时序的键盘/鼠标注入）。

> 当前状态：**v1 已完成**（2026-09-25）。自动化测试 164 项全绿；游戏内手动验收 MAN-01…MAN-10 全部通过。

## 快速开始

```powershell
# 图形界面（需要一个游戏之外的键盘/鼠标，用于选曲与控制）
python -m kouqin

# 命令行（在图形界面之前就能用；训练场里倒计时后开始演奏）
python -m kouqin check                       # 环境自检
python -m kouqin dry-run scores\twinkle.kq   # 打印事件序列，不注入
python -m kouqin play    scores\twinkle.kq   # 倒计时后真实演奏
```

**游戏内的控制手段是全局热键**（游戏里点不到本程序界面）：

| 热键 | 作用 |
|------|------|
| `Ctrl+Alt+P` | 开始 / 停止 |
| `Ctrl+Alt+U` | 暂停（＝静音）/ 继续 |
| `Ctrl+Alt+K` | 急停（立即松开所有键） |

热键可在「设置 → 全局热键」里修改，每个键旁有「检测」按钮验证是否被别的程序占用
（默认的 `Ctrl+Alt+L` 就曾被 QQ 占用，所以换成了 K）。

## 功能

- **曲谱**：文本简谱 `.kq`（可手写/粘贴）、`.kq.json`、**MIDI 导入**；界面里实时解析并在下方报错。
- **演奏**：精确时序注入；支持循环、速度 0.5×–2×、整体移调 ±12 半音；进度与当前音高亮。
- **范围**：低音 `1` 到两点 `1` 共 **37 个半音**全部可演奏（含所有升降音），超范围会在预览里标红并拒绝播放。
- **安全**：焦点守卫——只把按键发给「开始时的前台窗口」，离开即停并释放；任何退出路径都不残留按下的键。

## 乐器行为（2026-09-25 游戏内实测确认）

| 输入 | 含义 | 半音 |
|------|------|------|
| `z x c v b n m` | 中音区 `1 2 3 4 5 6 7` | `0,2,4,5,7,9,11` |
| `,` | 高八度 `1̇` | `12` |
| 按住鼠标左键 | 降调（降一个八度） | `−12` |
| 按住鼠标滚轮 | 半音（升半音） | `+1` |
| 按住鼠标右键 | 升调（升一个八度） | `+12` |

两个修饰键可叠加（左+中 = `−11`、右+中 = `+13`），因此**低音 `1` 到两点 `1` 的 37 个半音全部可演奏**。
权威来源：[config/instrument.json](config/instrument.json)，代码不硬编码这些数值。

## 目录结构

```text
kouqin/
  kouqin/            Python 包：core（领域逻辑）/ scores（曲谱读写）/ input（注入）/ player（播放引擎）/ hotkey（热键）/ ui（界面）
  config/            instrument.json（键位与乐器语义）、settings.json（界面与播放偏好）
  scores/            曲谱库（含小星星、半音阶自检、长音自检三支）
  tools/             P0 实验工具、打包脚本、MIDI 样例生成器
  docs/design/       设计、规格、测试计划、实验清单
  docs/harness/      进度、决策、错误记录
  tests/unit/        单元测试（164 项）
  tests/manual/      游戏内验收清单与记录
```

## 环境

- Windows 10/11 x64
- Python 3.13.12（`C:\Users\jimot\AppData\Local\Programs\Python\Python313\python.exe`）
- PySide6 6.11.1
- pytest 9.1.1

> 不需要 AutoHotkey：注入由 Python 的 ctypes `SendInput` 直接完成（2026-09-25 实测在游戏内生效）。

## 常用命令

```powershell
python -m pytest -q                 # 全部测试
python -m pytest tests/unit -q      # 单元测试
python -m compileall -q kouqin      # 语法检查
python -m kouqin                    # 启动图形界面
python tools\make_bundle.py --zip   # 打包到另一台机器（见 docs/RUN_ON_B.md）
```

## 文档

- 设计与实验：`docs/design/DESIGN_SUMMARY_FOR_OPENSPEC.md`
- 拷到游戏机运行：`docs/RUN_ON_B.md`（打包：`python tools/make_bundle.py --zip`）
- 当前进度：`docs/harness/PROGRESS.md`
- 架构决策：`docs/harness/DECISIONS.md`
- 错误记录：`docs/harness/ERRORS.md`
- Agent 行为指引：`AGENTS.md`

## 使用须知与风险

- 本工具只发送键盘/鼠标输入，不读写游戏内存、不修改游戏文件、不涉及反作弊绕过。
- 在游戏内使用自动输入存在被反作弊判定的风险，请自行评估；本工具定位为乐器演奏，不用于对战自动化。

## 许可

本仓库采用 **个人非商业使用许可**（[LICENSE](LICENSE)）：允许个人非商业目的的使用与修改，
**禁止再分发与任何商业用途**。

这不是 OSI 认可的开源许可，属于"源码可见"（source-available）授权。
本项目与任何游戏开发商、发行商及其关联方无任何关系，也未获其授权或认可。
