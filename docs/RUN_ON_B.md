# 在第二台机器（游戏机 B）上运行 —— 拷贝清单与步骤

- **日期**: 2026-09-25
- **适用**: 把本工程的 **P0 注入实验工具** 搬到另一台 Windows 机器，在真实游戏里做验证
- **分工前提**: 曲谱/编译/界面（Python + PySide6）留在开发机 A；**B 只负责「跑实验 + 报结果」**

---

## 1. 必须拷贝

| 路径 | 作用 | 必需 |
|---|---|---|
| `tools/p0_sendinput_demo.py` | P0 实验工具（**单文件自包含**，纯标准库） | ✅ |
| `docs/RUN_ON_B.md` | 本文件（B 上的操作说明） | 建议 |
| `tests/unit/test_p0_sendinput_demo.py`、`pytest.ini` | 仅当 B 上装了 pytest 想自检时 | 可选 |

> **只想拷一个文件也行**：`tools/p0_sendinput_demo.py` 不读配置、不依赖项目内其它文件、不需要 pip 安装任何包。
> 但请保持目录结构里 `tools\` 这一层（命令示例按它写），或者你按自己的路径调整命令。

## 2. B 上需要什么

- Windows 10/11 x64
- **Python 3.9+**（推荐 3.13；安装时务必勾选 `Add python.exe to PATH`）
  - **不需要 `pip install` 任何东西**，本工具只用标准库
- 游戏本体（能在训练场拿出乐器「口琴」）
- **不需要** AutoHotkey（本阶段用不到）

> 如果 B 上装不了 Python，告诉我 —— 我可以把同一套实验用 AutoHotkey v2 再写一份，
> B 上只需要 AutoHotkey（或拷一个便携版 exe）。

## 3. 目录结构（拷过去后的样子）

```text
<任意根目录>\kouqin\
  tools\p0_sendinput_demo.py
  README.txt                ← 本文件
  tests\unit\...            ← 可选
  pytest.ini                ← 可选
```

## 4. 操作顺序（约 15 分钟）

在 `<任意根目录>\kouqin\` 下打开 PowerShell，或在地址栏输入 `powershell` 回车。

1. **环境自检**

   ```powershell
   python tools\p0_sendinput_demo.py check
   ```

   看输出里的「管理员运行：是/否」。**若游戏是以管理员身份运行的，本脚本也必须用管理员终端跑**，
   否则 Windows 的 UIPI 会拦住注入。

2. **验证注入是否生效**

   ```powershell
   python tools\p0_sendinput_demo.py scale
   ```

   按 Enter 后有 5 秒倒计时 → 立刻切回游戏（拿出「口琴」，站在训练场/安全区）。
   应听到 `z x c v b n m ,` 依次上行 8 个音。
   **若完全没声音 → 记录现象（下面第 6 节），这一条最关键。**

3. **标定「左/中/右键」是几半音**（三次）

   ```powershell
   python tools\p0_sendinput_demo.py compare --button right
   python tools\p0_sendinput_demo.py compare --button middle
   python tools\p0_sendinput_demo.py compare --button left
   ```

   每轮先弹「按住该鼠标键 + z」的参考音，再逐个弹 8 个普通键（重复两轮）。
   你只需要回答：**参考音跟第几个普通键听起来完全一样？** 如果夹在两个之间，
   回答「在 z 和 x 之间」这种。

4. **最短可按时长**

   ```powershell
   python tools\p0_sendinput_demo.py hold-sweep
   ```

   同一个键依次按 20/30/40/50/80/120 ms（间隔 1.5 秒）。
   回答：**第几段开始能稳定听到声音？**（例如"第 3 段开始稳定"→ 40 ms）

5. **（可选）重复音与吞音**

   ```powershell
   python tools\p0_sendinput_demo.py key --key z --repeat 8 --hold-ms 60 --interval-ms 20
   ```

   听这 8 个连续的 z 是「8 个都清楚」还是「被吃掉/粘成一片」。

6. **（可选）长音是否被自动切断**

   游戏里手动按住一个键 3 秒、6 秒，听是否中途自己断掉。

安全提醒：

- `mouse --button left` 在游戏里可能就是**开火**，只在训练场/靶场用。
- 所有模式都会在退出（含 Ctrl+C）时释放仍按住的键。

## 5. 不想真发按键时

任何模式都可加 `--dry-run`，只打印将要发送的事件、不注入：

```powershell
python tools\p0_sendinput_demo.py --dry-run scale
```

## 6. 回传（B → A）

把这 6 项回来说清楚即可，A 侧负责填进 `config/instrument.json` 与设计文档：

| 待回填项 | 需要的回答 | 对应未知 |
|---|---|---|
| 管理员运行 | check 的输出 | — |
| `scale` 是否有声 | 有/无；无则描述现象（完全没反应 / 有乱音 / 只响一下） | U7 注入方式 |
| 右键 | 参考音＝第几个键（或夹在哪两个之间） | U1 |
| 中键 | 同上 | U1 |
| 左键 | 同上 | U1 |
| 左+右同时按住 + z | 与单独按住有区别吗 | U2 |
| `hold-sweep` | 第几段开始稳定出声 | U3 |
| `key` 连打（可选） | 8 个都清楚 / 有吞音 | U4 |
| 长按 3s / 6s（可选） | 是否自动切断 | U6 |

## 7. 不用拷的东西

| 不拷 | 原因 |
|---|---|
| `docs/harness/`、`docs/design/`、`AGENTS.md`、`README.md` | 开发与流程文档，留 A |
| `.git/` | 版本控制，留 A（本沙盒也不做 git 操作） |
| `__pycache__/`、`.pytest_cache/` | 缓存，A 上自动重建 |
| `config/`、`kouqin/`、`macro/` | **目前还不存在**（Step 4 实现后才会有），届时再按新说明拷贝 |

## 8. 另一种做法：整体拷贝

本工程当前体积只有几十 KB，**直接把整个 `kouqin` 文件夹拷过去**也完全可行（记得排除缓存目录）。
用打包脚本可以一次生成干净的可拷目录：

```powershell
python tools\make_bundle.py --zip
```
