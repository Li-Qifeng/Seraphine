"""快捷喊话子系统配置。与主配置 cfg 深度融合，保持单例干净与配置一致。"""
import json
import os
from app.common.config import cfg, LOCAL_PATH


class _ChatConfigProxy:
    """代理访问主配置 cfg，向后兼容现有 chat_cfg 接口。"""

    @property
    def enabled(self):
        return cfg.enableQuickChat

    @property
    def minIntervalMs(self):
        return cfg.quickChatMinIntervalMs

    @property
    def burstLimit(self):
        return cfg.quickChatBurstLimit

    @property
    def burstCooldownMs(self):
        return cfg.quickChatBurstCooldownMs

    @property
    def useClipboard(self):
        return cfg.quickChatUseClipboard

    def get(self, item):
        return cfg.get(item)

    def set(self, item, value, save=True):
        return cfg.set(item, value, save=save)


chat_cfg = _ChatConfigProxy()

# 兼容旧版 chat_config.json 存量迁移
_legacy_path = os.path.join(LOCAL_PATH, "chat_config.json")
if os.path.exists(_legacy_path):
    try:
        with open(_legacy_path, "r", encoding="utf-8") as _f:
            _legacy_data = json.load(_f).get("Chat", {})
            if "Enabled" in _legacy_data:
                cfg.set(cfg.enableQuickChat, bool(_legacy_data["Enabled"]))
            if "MinIntervalMs" in _legacy_data:
                cfg.set(cfg.quickChatMinIntervalMs, int(_legacy_data["MinIntervalMs"]))
            if "BurstLimit" in _legacy_data:
                cfg.set(cfg.quickChatBurstLimit, int(_legacy_data["BurstLimit"]))
            if "BurstCooldownMs" in _legacy_data:
                cfg.set(cfg.quickChatBurstCooldownMs, int(_legacy_data["BurstCooldownMs"]))
            if "UseClipboard" in _legacy_data:
                cfg.set(cfg.quickChatUseClipboard, bool(_legacy_data["UseClipboard"]))
    except Exception:
        pass
