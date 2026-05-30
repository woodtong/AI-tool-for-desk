"""
AI 提供者管理器 - 管理多个 AI 适配器的创建、选择和调用
"""
from .adapter import AIAdapter


class AIProviderManager:
    """AI 提供者管理器，负责创建和管理 AI 适配器实例"""

    def __init__(self, config_manager):
        """
        参数:
            config_manager: ConfigManager 实例
        """
        self._config = config_manager
        self._adapters = {}   # provider_id -> AIAdapter
        self._current_id = None  # 当前选中的提供者 ID

    def _get_or_create_adapter(self, provider_id):
        """按需创建单个适配器（懒加载）"""
        if provider_id not in self._adapters:
            provider = self._config.get_provider_by_id(provider_id)
            if provider:
                self._adapters[provider_id] = AIAdapter(provider)
        return self._adapters.get(provider_id)

    def get_adapters(self):
        """
        获取所有已配置的适配器（按需懒加载）

        返回:
            dict: {provider_id: AIAdapter}
        """
        providers = self._config.get_providers()
        for p in providers:
            pid = p["id"]
            self._get_or_create_adapter(pid)
        return self._adapters

    def get_current_adapter(self):
        """获取当前选中的适配器"""
        if self._current_id:
            adapter = self._get_or_create_adapter(self._current_id)
            if adapter:
                return adapter
        # 如果没有选中，取第一个可用的
        providers = self._config.get_providers()
        if providers:
            first = providers[0]
            self._current_id = first["id"]
            return self._get_or_create_adapter(first["id"])
        return None

    def set_current(self, provider_id):
        """设置当前选中的提供者"""
        adapter = self._get_or_create_adapter(provider_id)
        if adapter:
            self._current_id = provider_id
            self._config.set("last_selected_provider", provider_id)
            return True
        return False

    def get_current_provider_id(self):
        """获取当前提供者 ID"""
        return self._current_id

    def is_current_configured(self):
        """当前选中模型是否已配置 API key"""
        adapter = self.get_current_adapter()
        return adapter is not None and adapter.is_configured()

    def send_message_stream(self, messages):
        """
        使用当前选中的适配器发送流式消息

        参数:
            messages: list[dict] - 消息列表

        生成器产出:
            str: AI 回复片段
        """
        adapter = self.get_current_adapter()
        if adapter is None:
            yield "[错误] 未选择 AI 模型，请在搜索条幅中选择一个模型"
            return
        if not adapter.is_configured():
            yield f"[错误] API Key 未配置，请在 config.json 中配置 {adapter.name} 的 api_key"
            return

        yield from adapter.send_message_stream(messages)

    def build_and_send(self, text, image_base64=None):
        """
        构建消息体并发送

        参数:
            text: str - 用户文本
            image_base64: str or None - 图片 base64 数据

        生成器产出:
            str: AI 回复片段
        """
        adapter = self.get_current_adapter()
        if adapter is None:
            yield "[错误] 未选择 AI 模型"
            return

        if image_base64 and adapter.supports_images:
            messages = AIAdapter.build_image_message(text or "请分析这张图片", image_base64)
        else:
            messages = AIAdapter.build_text_message(text or "你好")

        yield from self.send_message_stream(messages)
