"""
配置管理器 - 负责加载/保存 config.json
支持通过点号语法读取嵌套配置（如 "providers.openai.api_key"）
"""
import json
import os

# 默认配置模板
DEFAULT_CONFIG = {
    # 首次运行标记（首次运行显示搜索条幅，之后直接显示对话窗口）
    "first_run": True,
    # 上次选中的 AI 提供者名称
    "last_selected_provider": "",
    # 全局快捷键配置
    # 注意: Win+Shift+S 被 Windows 截图工具占用，改为 Win+Shift+Z
    "hotkeys": {
        "show_banner":   {"mod": "win+shift", "key": "f"},
        "screenshot":    {"mod": "win+shift", "key": "z"},
        "text_capture":  {"mod": "win+shift", "key": "x"}
    },
    # 全局系统提示词（所有模型共用，每个模型可单独覆盖）
    "system_prompt": "你是一个有用的 AI 助手。回答要简洁清晰。",
    # AI 提供者列表
    "providers": [
        {
            "id": "openai",
            "name": "OpenAI",
            "enabled": True,
            "api_key": "",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o",
            "supports_images": True,
            "system_prompt": ""
        },
        {
            "id": "deepseek",
            "name": "DeepSeek",
            "enabled": True,
            "api_key": "",
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "supports_images": False,
            "system_prompt": ""
        },
        {
            "id": "custom",
            "name": "自定义 API",
            "enabled": True,
            "api_key": "",
            "base_url": "",
            "model": "",
            "supports_images": False,
            "system_prompt": ""
        }
    ],
    # 知识库设置
    "knowledge_base": {
        "enabled": False,
        "path": ""
    },
    # 对话窗口设置
    "chat_window": {
        "opacity": 0.92,
        "width": 600,
        "height": 520,
        "pos_x": None,
        "pos_y": None,
        "always_on_top": True
    }
}


def _deep_merge(default, override):
    """递归合并两个字典，override 的值优先"""
    result = default.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class ConfigManager:
    """配置管理器，提供配置的读取、写入、修改功能"""

    def __init__(self, config_path=None):
        if config_path is None:
            config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")
        self.config_path = config_path
        self.config = self._load()

    def _load(self):
        """从文件加载配置，与 DEFAULT_CONFIG 深层合并后返回"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
            except (json.JSONDecodeError, IOError):
                return DEFAULT_CONFIG.copy()

            # 深层合并：以 DEFAULT_CONFIG 为基底，已存配置覆盖其上
            merged = _deep_merge(DEFAULT_CONFIG, loaded)

            # 单独处理 providers 列表：为每个 provider 补全 DEFAULT_CONFIG 中的字段
            default_providers = {p["id"]: p for p in DEFAULT_CONFIG["providers"]}
            for p in merged.get("providers", []):
                pid = p.get("id")
                if pid and pid in default_providers:
                    for key, val in default_providers[pid].items():
                        if key not in p:
                            p[key] = val

            return merged

        return DEFAULT_CONFIG.copy()

    def save(self):
        """保存配置到文件"""
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)

    def get(self, key, default=None):
        """
        获取配置项，支持点号路径语法
        示例: get("providers.openai.api_key")
        """
        keys = key.split(".")
        value = self.config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def set(self, key, value):
        """
        设置配置项，支持点号路径语法
        示例: set("providers.openai.api_key", "sk-xxx")
        """
        keys = key.split(".")
        target = self.config
        for k in keys[:-1]:
            target = target.setdefault(k, {})
        target[keys[-1]] = value
        self.save()

    def get_providers(self):
        """获取启用的 AI 提供者列表"""
        return [p for p in self.config.get("providers", []) if p.get("enabled", True)]

    def get_provider_by_id(self, provider_id):
        """根据 ID 获取提供者配置"""
        for p in self.config.get("providers", []):
            if p["id"] == provider_id:
                return p
        return None

    def update_provider(self, provider_id, updates):
        """更新指定提供者的配置"""
        for p in self.config.get("providers", []):
            if p["id"] == provider_id:
                p.update(updates)
                self.save()
                return True
        return False

    def get_system_prompt(self, provider_id=None):
        """
        获取系统提示词：全局 + 模型专属提示词拼接在一起发送。
        例如全局为"你是 AI"，模型为"用中文回答"，最终为"你是 AI\n用中文回答"。
        """
        parts = []

        # 全局提示词
        global_prompt = self.get("system_prompt", "").strip()
        if global_prompt:
            parts.append(global_prompt)

        # 模型专属提示词（附加到全局后面，一同发送）
        if provider_id:
            provider = self.get_provider_by_id(provider_id)
            if provider:
                prov_prompt = provider.get("system_prompt", "").strip()
                if prov_prompt:
                    parts.append(prov_prompt)

        return "\n".join(parts) if parts else "你是一个有用的 AI 助手。回答要简洁清晰。"

    def set_global_system_prompt(self, text):
        """设置全局系统提示词"""
        self.set("system_prompt", text)

    def set_provider_system_prompt(self, provider_id, text):
        """设置某个模型的系统提示词覆盖"""
        self.update_provider(provider_id, {"system_prompt": text})

    def mark_first_run_done(self):
        """标记首次运行已完成"""
        self.set("first_run", False)
