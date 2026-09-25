# Error Index

| ID | 标题 | 状态 | 发现日期 | 解决日期 | 细节文件 |
|----|------|------|----------|----------|----------|
| ERR-001 | 在工作区执行 `git init` 导致沙盒环境刷新失败，全部命令无法启动 | Resolved | 2026-09-25 | 2026-09-25 | [details](errors/ERR-001.md) |
| ERR-002 | `git push` 被 GitHub 以 GH007 拒绝（作者邮箱属于受保护的私有邮箱） | Resolved | 2026-09-25 | 2026-09-25 | [details](errors/ERR-002.md) |
| ERR-003 | 焦点守卫连续两次误判（根因：Win32 函数缺 ctypes 签名导致句柄截断） | Resolved | 2026-09-25 | 2026-09-25 | [details](errors/ERR-003.md) |

状态取值：`Unresolved` / `Resolved` / `WontFix` / `Closed`。

## 环境约定

- Agent **不得**在本工作区执行 `git init`（见 ERR-001）：由沙盒账户创建的 `.git` 会使环境刷新失败、
  命令工具完全不可用。
- 需要版本控制时由用户在本地终端初始化；日常的 `git add/commit` 也由用户执行，Agent 只提供建议命令。
- **邮箱口径**：GitHub 若开启 "Keep my email addresses private"，本地 `user.email` 必须同步改为
  GitHub 给出的 noreply 地址，否则推送会被 GH007 拒绝（见 ERR-002）。
  本工程统一使用：`332089221+SSSS-TY@users.noreply.github.com`。
