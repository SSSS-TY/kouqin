# 在第二台机器（游戏机 B）上运行 —— 拷贝清单与步骤

- **日期**: 2026-09-25（随 M3 完成更新）
- **适用**: 把本工程的**命令行演奏工具**搬到另一台 Windows 机器上实测
- **分工前提**: 开发、编译、界面留在 A 机；**B 机只负责「跑 + 听 + 反馈」**

---

## 1. 要拷什么（已由打包脚本保证）

一条命令生成干净的可拷目录（再加 `--zip` 得到单个压缩包）：

```powershell
cd D:\codex\kouqin
python tools\make_bundle.py --zip
```

产物：`%TEMP%\kouqin_bundle\`（24 个文件，约 95 KB）+ `kouqin_bundle.zip`（约 43 KB）。

| 打包后路径 | 作用 | 必需 |
|---|---|---|
| `kouqin\` | **运行包本体**（core / scores / input / player / cli） | ✅ |
| `config\instrument.json` | 乐器映射（实测校准结果，唯一权威来源） | ✅ |
| `config\settings.json` | 播放参数与热键 | ✅ |
| `scores\twinkle.kq` | 第一首验收曲目（小星星） | ✅ |
| `tools\p0_sendinput_demo.py` | P0 实验工具（含 P0-7 长音衰减测量） | 建议 |
| `LICENSE` | 许可（个人非商业） | 建议 |
| `README.txt` | 本文件 | ✅ |

**当前不需要**：AutoHotkey、PySide6、任何 `pip install`。
命令行模式只用 Python 标准库——已用 `python -S`（关闭 site-packages）实测可运行。

> 图形界面（M4）完成后，B 机上还需要 PySide6（届时会更新本文件的清单）。

## 2. B 机上需要什么

- Windows 10/11 x64
- **Python 3.9+**（推荐 3.13；安装时勾选 `Add python.exe to PATH`）
- 游戏本体（能在训练场拿出「口琴」）

## 3. 目录结构（拷过去后的样子）

```text
<任意根目录>\kouqin\
  README.txt
  LICENSE
  config\instrument.json
  config\settings.json
  scores\twinkle.kq
  tools\p0_sendinput_demo.py
  kouqin\__main__.py
  kouqin\cli.py
  kouqin\core\...
  kouqin\scores\...
  kouqin\input\...
  kouqin\player\...
```

**【硬要求】** 必须在 `kouqin\` 这一层执行命令（`python -m kouqin` 需要当前目录能看到 `kouqin\` 包）。

## 4. 操作顺序（约 15 分钟）

在 `<任意根目录>\kouqin\` 打开 PowerShell（地址栏输入 `powershell` 回车即可）。

1. **环境自检**

   ```powershell
   python -m kouqin check
   ```

   输出里 `管理员运行` 与 `可注入前台`。**若游戏以管理员运行，本终端也必须以管理员打开**，
   否则 Windows 的 UIPI 会拦住注入。

2. **先看事件序列（不注入，安全）**

   ```powershell
   python -m kouqin dry-run scores\twinkle.kq
   ```

   应看到「可演奏音：42　事件：84　总长：28.77 秒」以及逐个事件的时间与动作。
   这一步用来确认：曲谱解析对了、音高映射对了、时序合理。

3. **真演奏（训练场！）**

   ```powershell
   python -m kouqin play scores\twinkle.kq
   ```

   按提示切回游戏、拿出「口琴」。倒计时结束后开始演奏；`Ctrl+C` 会立刻停止并释放所有按键。

   **听这几点**：旋律是不是小星星？音高有没有明显错音？节奏是否均匀？长音是否拖得住？

4. **升降音与八度自检（重要）**

   ```powershell
   python -m kouqin play scores\chromatic.kq
   ```

   这是从低音 `1` 逐半音上行到两点 `1` 的半音阶，**会依次用上全部 6 种修饰组合**
   （无 / 左键 / 中键 / 右键 / 左+中 / 中+右）。演奏时对照游戏内显示的简谱：

   - 每个音都响 → 鼠标修饰键注入正常；
   - 音高逐级升高、没有跳音或重复 → 修饰键切换时序正确；
   - 少数音会用「等音写法」（如 `#3` 实际用 `4` 演奏，游戏显示 4 而非 #3），音高对即可。

5. **图形界面（需要额外装 PySide6）**

   ```powershell
   python -m pip install PySide6      # 约 100 MB，只需装一次
   python -m kouqin                   # 不带参数 = 启动界面
   ```

   界面里有：曲谱库（含「N 个音不可达」标记）、简谱编辑与实时报错、音符预览、播放控制条
   （开始/暂停/停止/循环/速度/移调）、设置（播放参数、热键、键位表）、校准（试拍 + 回填半音数）。

   **不装 PySide6 也能用**：命令行模式（上面第 1–4 步）纯标准库即可运行。

6. **（可选）P0-7 长音衰减测量**

   ```powershell
   python tools\p0_sendinput_demo.py sustain
   ```

   依次按住同一个键 2/4/6/8/10/12 秒（每段之间停 2 秒）。
   回答：**从第几段开始，末尾明显变小或听不见？**

## 5. 回传（B → A）

把下面几项说清楚即可，A 机负责回填配置与文档：

| 待回填项 | 需要的回答 |
|---|---|
| 管理员运行 / 可注入 | `check` 的输出 |
| `dry-run` | 是否与预期一致（可整段贴回） |
| `play` 效果 | 旋律是否正确、有无错音、节奏是否均匀、是否漏音 |
| 错误现象 | 完全没声 / 只响一下 / 音高不对 / 卡顿 —— 尽量描述在哪一小节 |
| P0-7 | 第几段开始明显衰减 |

## 6. 不用拷的东西

| 不拷 | 原因 |
|---|---|
| `docs\`、`AGENTS.md`、`README.md` | 开发与流程文档，留 A 机（`docs/RUN_ON_B.md` 已作为 `README.txt` 带走） |
| `.git\`、`.gitignore`、`.gitattributes` | 版本控制，留 A 机 |
| `tests\`、`pytest.ini` | 回归测试；确实想在 B 上跑可加 `--with-tests`（需装 pytest） |
| `tools\make_test_midi.py`、`tools\make_bundle.py` | 只在 A 机生成素材/打包用 |
| `measurements\`、原始素材 | 本工程暂无 |

## 7. 另一种做法：整体拷贝 / 用 git

- 整个仓库也才 100 KB 量级，**直接拷整个文件夹**同样可行（记得排除 `__pycache__`、`.pytest_cache`）。
- 用 git 更省事：B 机上 `git clone https://github.com/SSSS-TY/kouqin`，
  但仓库是**个人非商业许可**的公开仓库，克隆仅限你本人自用。
