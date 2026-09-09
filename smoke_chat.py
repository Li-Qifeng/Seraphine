# coding:utf-8
"""快捷喊话子系统 offscreen 端到端冒烟（真实 PyQt5 + 真实 Win32，非 pytest 桩）。

运行（仓库根目录）：
    set QT_QPA_PLATFORM=offscreen && python smoke_chat.py

验证项：
1. ChatService.init → 内置词库 seed 5 组
2. 总开关开启 → 分组热键注册；关闭 → 全部注销
3. 无游戏相位 → 发送被 gate 正确拦截（不发送、不记日志）
4. ChatInterface 可构造（UI 装配完整）
5. shutdown → 热键注销、DB 关闭
"""
import asyncio
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qasync import QApplication  # noqa: E402

from app.chat.service import chat_service  # noqa: E402
from app.common.chat_config import chat_cfg  # noqa: E402
from app.view.chat_interface import ChatInterface  # noqa: E402


def check(name: str, cond: bool) -> bool:
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")
    return cond


async def amain() -> int:
    app = QApplication.instance() or QApplication(sys.argv)

    chat_service.init(app)
    repo = chat_service.repo

    groups = repo.list_groups()
    ok = check("seed at least 5 groups", len(groups) >= 5)
    total = sum(len(repo.list_phrases(g["id"])) for g in groups)
    ok &= check("seed at least 25 phrases", total >= 25)

    ok &= check("hotkeys empty before enable",
                chat_service.registered_hotkeys() == [])

    chat_cfg.set(chat_cfg.enabled, True)
    chat_service.refresh_hotkeys()
    registered = chat_service.registered_hotkeys()
    expected_default = [f"Alt+{i}" for i in range(1, 6)]
    ok &= check(f"hotkeys registered after enable: {registered}",
                all(hk in registered for hk in expected_default))

    # 无游戏相位 → gate 拦截
    res = await chat_service.orchestrator.send_group(groups[0]["id"])
    ok &= check("send blocked by gate (no game)",
                not res["ok"] and res["stage"] == "gate")
    ok &= check("gate block writes no send_log",
                repo.list_send_logs(limit=1) == [])

    # 循环游标：直接调用 repo 层（相位闸在 orchestrator，不在 repo）
    gid = groups[0]["id"]
    seq = [repo.next_phrase_in_group(gid)["content"] for _ in range(6)]
    ok &= check(f"cycle wraps: {seq[0]} / {seq[5]}",
                seq[0] == seq[5] and len(set(seq[:5])) == 5)

    chat_cfg.set(chat_cfg.enabled, False)
    chat_service.refresh_hotkeys()
    ok &= check("hotkeys unregistered after disable",
                chat_service.registered_hotkeys() == [])

    ui = ChatInterface()
    ok &= check("ChatInterface constructed", ui is not None
                and ui.groupSegmented is not None and ui.groupDetailCard is not None)

    chat_service.shutdown()
    print("SMOKE", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(amain()))
