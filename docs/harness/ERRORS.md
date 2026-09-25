# Error Index

| ID | 标题 | 状态 | 发现日期 | 解决日期 | 细节文件 |
|----|------|------|----------|----------|----------|
| ERR-001 | 在工作区执行 `git init` 导致沙盒环境刷新失败，全部命令无法启动 | Resolved | 2026-09-25 | 2026-09-25 | [details](errors/ERR-001.md) |

状态取值：`Unresolved` / `Resolved` / `WontFix` / `Closed`。

## 环境约定

- Agent **不得**在本工作区执行 `git init`（见 ERR-001）：由沙盒账户创建的 `.git` 会使环境刷新失败、
  命令工具完全不可用。
- 需要版本控制时由用户在本地终端初始化；日常的 `git add/commit` 也由用户执行，Agent 只提供建议命令。
