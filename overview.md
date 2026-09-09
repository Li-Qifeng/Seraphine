# 快捷喊话子系统 — 交付总览

## 本轮完成

在 `feat/in-game-chat` 分支上按已收敛规格重建局内快捷喊话子系统（旧实现随 worktree 丢失，本次为按调研文档重写）：

| 层 | 内容 |
|---|---|
| 存储 | `app/chat/store/`：`seraphine_chat.db` 独立库（只增不删、RLock）、CRUD/组内循环游标/send_log(30天)、内置词库 5 组 25 条 seed（dirty 保护的升级合并） |
| 领域 | `app/chat/domain/`：限流抖动 `Rhythm`（硬下限 600ms）、热键冲突硬拦截 `keys`、`SendOrchestrator` 唯一发送出口（阶段闸→循环取词→节奏→双通道→记账） |
| 引擎 | `app/chat/engine/`：SendInput Unicode 逐字 + Enter 补扫描码 + 剪贴板整条（默认关）、前台判定、`HotkeyManager`（注册时兜底校验） |
| 接入 | `service.py` 单例门面（零侵入接线）、`chat_config.json`（默认关）、设置页「快捷喊话」导航页（分组管理/循环预览/参数/日志）、双主题 QSS、`connector.sendChatMessage`、requirements 补 pywin32 |

## 验证证据

- `pytest tests/`：**384 passed**（基线 326 → +58，含 store/domain/engine 三份契约测试）
- `ruff check app/ tests/`：全绿
- offscreen 端到端冒烟（`smoke_chat.py`，真实 Qt+Win32）：seed/热键注册注销/gate 拦截/循环回绕/UI 构造 **9/9 PASS**
- Python 3.8 兼容 grep：无 `list[...]`/`X|Y`

## 关键决策（用户拍板）

- 热键语义 = 分组热键 + 组内循环（D11）；双通道生效矩阵 = 局内/BP/房间；安全模块整个不做（D12，风险用户自担）；**敏感词混淆转换器属审核对抗红线，已拒绝且未来不可做**。
- 范围外（后续迭代）：迷你指令窗、连发、变量引擎、话术包导入导出。

## 待办（用户侧）

1. 按 `document/LOL_快捷喊话_真机验收手册.md` 在训练模式验收（重点：局内 20 次成功率 ≥95%、Lobby 会话类型——若不发，把日志里 `available=[...]` 反馈给我调 `_CONV_TYPES_BY_PHASE`）。
2. 验收通过后合并分支、改 VERSION 发版（CI 自动出包）。

## 主要文件

- `document/LOL_快捷喊话_设计规格_v1.0.md` — 需求规格（已逐条确认）
- `document/LOL_快捷喊话_真机验收手册.md` — 真机验收清单
- `app/chat/`、`app/view/chat_interface.py`、`app/common/chat_config.py`、`smoke_chat.py`
- `tests/test_chat_{store,domain,engine}.py`
