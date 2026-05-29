"""
AI API 适配器 - 封装 OpenAI 兼容接口调用
支持 OpenAI、DeepSeek、自定义 OpenAI 兼容 API
统一流式输出接口
"""


class AIAdapter:
    """AI 适配器，封装 OpenAI 兼容 API 的调用"""

    def __init__(self, provider_config):
        """
        初始化适配器（延迟创建 OpenAI 客户端，避免无 api_key 时报错）

        参数:
            provider_config: dict - 包含 api_key, base_url, model, supports_images 等
        """
        self.config = provider_config
        self._client = None
        self.model = provider_config.get("model", "gpt-4o")
        self.supports_images = provider_config.get("supports_images", False)

    @property
    def client(self):
        """延迟初始化 OpenAI 客户端"""
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(
                api_key=self.config.get("api_key", ""),
                base_url=self.config.get("base_url", "https://api.openai.com/v1"),
            )
        return self._client

    @property
    def name(self):
        return self.config.get("name", "未知模型")

    def send_message_stream(self, messages):
        """
        发送消息并流式获取回复

        参数:
            messages: list[dict] - OpenAI 格式的消息列表
                      [{"role": "user", "content": "你好"}]

        生成器产出:
            str: AI 回复的文本片段
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
                timeout=60,
            )

            for chunk in response:
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            yield f"\n\n[错误] API 调用失败: {str(e)}"

    def send_message(self, messages):
        """
        非流式发送消息（一次性获取完整回复）

        参数:
            messages: list[dict] - 消息列表

        返回:
            str: 完整回复文本
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=False,
                timeout=60,
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"[错误] API 调用失败: {str(e)}"

    def is_configured(self):
        """检查是否已配置 API key"""
        api_key = self.config.get("api_key", "")
        return bool(api_key) and api_key != ""

    @staticmethod
    def build_image_message(text, image_base64):
        """
        构建包含图片的消息体（用于视觉模型）

        参数:
            text: str - 文本消息
            image_base64: str - base64 编码的图片数据

        返回:
            list[dict]: OpenAI 多模态消息格式
        """
        return [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": text},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_base64}"
                        },
                    },
                ],
            }
        ]

    @staticmethod
    def build_text_message(text):
        """构建纯文本消息"""
        return [{"role": "user", "content": text}]
