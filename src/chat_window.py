"""
对话窗口 - 与 AI 交互的主界面
- 可拖动位置、调整大小
- 透明度可调（0.3 ~ 1.0）
- 始终置顶
- 简洁的消息气泡布局
- 流式输出显示
- 对话历史记录（上下文）
"""
import logging
import markdown
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextBrowser,
    QTextEdit, QPushButton, QSlider, QLabel, QSizeGrip,
    QScrollArea, QFrame, QApplication, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer, QRect, QSize
from PySide6.QtGui import (
    QFont, QTextCursor, QPainter, QPen, QColor, QMouseEvent,
    QPixmap, QIcon, QCursor
)
from src.ai_providers.adapter import AIAdapter
from src.knowledge_base import load_knowledge_base, invalidate_cache

logger = logging.getLogger(__name__)


# ==================== AI 响应工作线程 ====================

class AIResponseWorker(QThread):
    """AI 流式响应的工作线程，避免阻塞 UI"""

    # 接收到新的文本片段
    chunk_received = Signal(str)
    # 流式输出完成
    finished = Signal()
    # 发生错误
    error = Signal(str)

    def __init__(self, provider_manager, messages):
        super().__init__()
        self._manager = provider_manager
        self._messages = messages

    def run(self):
        """在线程中执行流式 API 调用"""
        try:
            for chunk in self._manager.send_message_stream(self._messages):
                self.chunk_received.emit(chunk)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))


# ==================== 自定义标题栏 ====================

class TitleBar(QWidget):
    """可拖动的自定义标题栏"""

    def __init__(self, title="AI 助手", parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        self._parent = parent
        self._dragging = False
        self._drag_pos = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 6, 0)

        # 标题文字
        self.title_label = QLabel(title)
        self.title_label.setObjectName("titleLabel")
        layout.addWidget(self.title_label)

        layout.addStretch()

        # 最小化按钮
        self.btn_min = QPushButton("─")
        self.btn_min.setObjectName("titleBtn")
        self.btn_min.setFixedSize(30, 26)
        self.btn_min.clicked.connect(self._on_minimize)
        layout.addWidget(self.btn_min)

        # 最大化/还原按钮
        self.btn_max = QPushButton("□")
        self.btn_max.setObjectName("titleBtn")
        self.btn_max.setFixedSize(30, 26)
        self.btn_max.clicked.connect(self._on_toggle_maximize)
        layout.addWidget(self.btn_max)

        # 关闭按钮
        self.btn_close = QPushButton("×")
        self.btn_close.setObjectName("titleBtnClose")
        self.btn_close.setFixedSize(30, 26)
        self.btn_close.clicked.connect(self._on_close)
        layout.addWidget(self.btn_close)

    def set_title(self, text):
        """设置标题文字"""
        self.title_label.setText(text)

    def _on_minimize(self):
        """最小化到托盘（隐藏窗口而非最小化）"""
        if self._parent:
            self._parent.hide()

    def _on_toggle_maximize(self):
        """切换最大化/还原"""
        if self._parent:
            if self._parent.isMaximized():
                self._parent.showNormal()
            else:
                self._parent.showMaximized()

    def _on_close(self):
        """关闭按钮 - 隐藏到系统托盘"""
        if self._parent:
            self._parent.hide()

    def mousePressEvent(self, event):
        """鼠标按下：开始拖动"""
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        """鼠标移动：拖动窗口"""
        if self._dragging and self._parent:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self._parent.move(self._parent.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        """鼠标释放：停止拖动"""
        if event.button() == Qt.LeftButton:
            self._dragging = False


# ==================== 消息气泡组件 ====================

class MessageBubble(QFrame):
    """单条消息的气泡显示"""

    def __init__(self, role, content, is_streaming=False):
        """
        参数:
            role: "user" 或 "assistant"
            content: str - 消息内容（markdown 格式）
            is_streaming: bool - 是否正在流式输出
        """
        super().__init__()
        self._role = role
        self._content = content
        self._is_streaming = is_streaming
        self._setup_ui()

    def _setup_ui(self):
        """初始化气泡布局"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        # 角色标签
        role_text = "🫵 你" if self._role == "user" else "🤖 AI"
        label = QLabel(role_text)
        label.setObjectName(f"roleLabel_{self._role}")
        label.setStyleSheet(
            "font-size: 12px; font-weight: bold; color: #888;"
            if self._role == "assistant" else
            "font-size: 12px; font-weight: bold; color: #4fc3f7;"
        )
        layout.addWidget(label)

        # 内容显示（使用 QTextBrowser 支持 HTML）
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.browser.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # 自适应高度
        self.browser.document().setDefaultStyleSheet(
            "body { color: #e0e0e0; font-size: 13px; }"
            "pre { background: #1e1e1e; padding: 10px; border-radius: 4px; overflow-x: auto; }"
            "code { background: #1e1e1e; padding: 1px 4px; border-radius: 3px; font-size: 12px; }"
            "p { margin: 4px 0; }"
            "h1, h2, h3, h4 { color: #e0e0e0; }"
            "a { color: #4fc3f7; }"
        )
        self.update_content(self._content)
        layout.addWidget(self.browser)

        # 流式输出指示器
        self.streaming_indicator = QLabel("⏳ AI 正在回复...")
        self.streaming_indicator.setStyleSheet("color: #888; font-size: 11px; font-style: italic;")
        self.streaming_indicator.setVisible(self._is_streaming)
        layout.addWidget(self.streaming_indicator)

    def update_content(self, content):
        """更新消息内容（用于流式输出时增量更新）"""
        self._content = content
        if self._role == "assistant":
            # AI 回复：将 markdown 转为 HTML
            html = markdown.markdown(
                content,
                extensions=["fenced_code", "codehilite", "tables"]
            )
            html = f"<div style='color:#e0e0e0; line-height:1.6;'>{html}</div>"
        else:
            # 用户消息：纯文本简单转 HTML
            html = f"<div style='color:#e0e0e0; line-height:1.6;'>{content}</div>"

        self.browser.setHtml(html)

        # 调整浏览器高度以适应内容
        doc = self.browser.document()
        doc.setTextWidth(self.browser.viewport().width())
        height = doc.size().height()
        self.browser.setFixedHeight(int(height) + 10)

    def set_streaming(self, streaming):
        """设置流式输出状态"""
        self._is_streaming = streaming
        self.streaming_indicator.setVisible(streaming)

    def resizeEvent(self, event):
        """窗口大小变化时重新计算浏览器高度，确保文字换行正确"""
        super().resizeEvent(event)
        doc = self.browser.document()
        doc.setTextWidth(self.browser.viewport().width())
        h = doc.size().height()
        self.browser.setFixedHeight(int(h) + 10)


# ==================== 主对话窗口 ====================

class ChatWindow(QWidget):
    """
    主对话窗口，与 AI 进行对话的主界面
    - 自由拖动/缩放位置
    - 透明度滑块
    - 流式消息显示
    - 对话历史维护
    """
    # 窗口关闭时发射（隐藏到托盘而非退出）
    window_hidden = Signal()

    # 边距大小（像素），用于检测边缘缩放
    RESIZE_MARGIN = 6
    MIN_WIDTH = 260
    MIN_HEIGHT = 300
    # 低于此宽度时隐藏模型名称标签
    MODEL_LABEL_HIDE_WIDTH = 340
    # 最大保留历史对话对数（超出丢弃最早的）
    MAX_HISTORY_PAIRS = 10

    def __init__(self, provider_manager, config_manager, parent=None):
        super().__init__(parent)
        self._provider_mgr = provider_manager
        self._config = config_manager

        # 对话历史: list of {"role": str, "content": str}
        self._history = []

        # AI 响应工作线程
        self._worker = None
        # 当前正在流式输出的消息气泡
        self._current_stream_bubble = None
        # 当前累积的 AI 回复文本
        self._current_response = ""

        # 流式渲染节流：50ms 内多次 chunk 只渲染一次
        self._render_pending = False
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._flush_render)

        self._setup_ui()
        self._load_config()
        self._apply_style()

    def _setup_ui(self):
        """初始化界面"""
        self.setWindowTitle("AI 助手")
        # 无边框、置顶、工具窗口
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ====== 标题栏 ======
        self.title_bar = TitleBar("AI 助手", self)
        main_layout.addWidget(self.title_bar)

        # ====== 控制栏（透明度 + 模型信息） ======
        control_bar = QWidget()
        control_bar.setObjectName("controlBar")
        control_bar.setFixedHeight(32)
        ctrl_layout = QHBoxLayout(control_bar)
        ctrl_layout.setContentsMargins(12, 0, 12, 0)

        ctrl_layout.addWidget(QLabel("透明度:"))
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(30, 100)
        self.opacity_slider.setValue(92)
        self.opacity_slider.setFixedWidth(100)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        ctrl_layout.addWidget(self.opacity_slider)

        self.opacity_label = QLabel("0.92")
        self.opacity_label.setFixedWidth(32)
        ctrl_layout.addWidget(self.opacity_label)

        ctrl_layout.addStretch()

        # 当前模型标签（允许收缩到零宽，窄窗口时由 resizeEvent 隐藏）
        self.model_label = QLabel("模型: 未选择")
        self.model_label.setObjectName("modelLabel")
        self.model_label.setMinimumWidth(0)
        self.model_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        ctrl_layout.addWidget(self.model_label)

        # 清空上下文按钮
        self.clear_btn = QPushButton("🗑 清空上下文")
        self.clear_btn.setObjectName("clearCtxBtn")
        self.clear_btn.setFixedHeight(22)
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.clicked.connect(self._on_clear_context)
        ctrl_layout.addWidget(self.clear_btn)

        main_layout.addWidget(control_bar)

        # ====== 消息显示区域 ======
        self.messages_container = QWidget()
        self.messages_container.setObjectName("messagesContainer")
        self.msg_layout = QVBoxLayout(self.messages_container)
        self.msg_layout.setContentsMargins(8, 8, 8, 8)
        self.msg_layout.setSpacing(8)
        self.msg_layout.setAlignment(Qt.AlignTop)

        # 滚动区域包裹消息容器
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.messages_container)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        main_layout.addWidget(self.scroll_area, 1)

        # ====== 输入区域 ======
        input_area = QWidget()
        input_area.setObjectName("inputArea")
        input_layout = QHBoxLayout(input_area)
        input_layout.setContentsMargins(8, 6, 8, 6)
        input_layout.setSpacing(6)

        self.input_edit = QTextEdit()
        self.input_edit.setPlaceholderText("输入消息... (Ctrl+Enter 发送)")
        self.input_edit.setFixedHeight(40)
        self.input_edit.setAcceptRichText(False)
        self.input_edit.installEventFilter(self)
        input_layout.addWidget(self.input_edit)

        self.send_btn = QPushButton("发送")
        self.send_btn.setObjectName("sendBtn")
        self.send_btn.setFixedSize(60, 36)
        self.send_btn.clicked.connect(self._on_send_message)
        input_layout.addWidget(self.send_btn)

        main_layout.addWidget(input_area)

        # ====== 右下角拖拽手柄 ======
        self.size_grip = QSizeGrip(self)
        self.size_grip.setFixedSize(16, 16)
        self.size_grip.setStyleSheet(
            "QSizeGrip { background-color: transparent; }"
            "QSizeGrip::handle { width: 0; }"
        )

        # 欢迎消息
        self._add_welcome_message()

        # 设置窗口最小尺寸（布局可能会推高最小值，显式覆盖）
        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)

    def _add_welcome_message(self):
        """添加欢迎消息"""
        welcome = (
            "## 👋 欢迎使用 AI 桌面助手\n\n"
            "### 快捷键说明:\n"
            "| 快捷键 | 功能 | 使用方式 |\n"
            "|--------|------|---------|\n"
            "| **Win+Shift+F** | 选择 AI 模型 | 弹出条幅选择模型 |\n"
            "| **Win+Shift+Z** | 截图分析 | 屏幕出现遮罩 → 拖拽框选区域 → 自动发送给 AI |\n"
            "| **Win+Shift+X** | 选取文字 | 先选中任意文字 → 按快捷键 → 自动发送给 AI |\n\n"
            "### 使用步骤:\n"
            "1. 按 **Win+Shift+F** 选择一个 AI 模型\n"
            "2. 在下方输入框打字按 **Ctrl+Enter** 发送\n"
            "3. 或按 **Win+Shift+Z** 截图发送给 AI 分析\n"
            "4. 或选中文字后按 **Win+Shift+X** 发送\n\n"
            "*点击右下角系统托盘图标可随时切换窗口。*"
        )
        self._add_message("assistant", welcome, is_welcome=True)

    def _on_opacity_changed(self, value):
        """透明度滑块变化"""
        opacity = value / 100.0
        self.setWindowOpacity(opacity)
        self.opacity_label.setText(f"{opacity:.2f}")
        self._config.set("chat_window.opacity", opacity)

    def _on_send_message(self):
        """发送按钮点击 / Ctrl+Enter 触发"""
        if self._worker and self._worker.isRunning():
            return  # 正在回复，不允许发送新消息

        text = self.input_edit.toPlainText().strip()
        if not text:
            return

        # 清空输入框
        self.input_edit.clear()

        # 检查是否已选择 AI 模型
        if not self._provider_mgr.get_current_adapter():
            self._add_message("assistant", "⚠️ **请先按 Win+Shift+F 选择一个 AI 模型**")
            return

        # 检查 API Key 是否配置
        if not self._provider_mgr.is_current_configured():
            adapter = self._provider_mgr.get_current_adapter()
            model_name = adapter.name if adapter else "当前"
            self._add_message("assistant", f"⚠️ **{model_name} 的 API Key 未配置**\n\n请在 config.json 中添加 api_key，或通过设置界面配置。")
            return

        # 添加用户消息到对话
        self._add_message("user", text)
        self._history.append({"role": "user", "content": text})

        # 创建 AI 回复消息气泡
        self._current_response = ""
        self._current_stream_bubble = self._add_message("assistant", "", is_streaming=True)

        # 启动 AI 响应线程
        self._start_ai_worker()

    def _start_ai_worker(self):
        """启动 AI 响应线程"""
        # 构建消息列表（包含历史上下文）
        provider_id = self._provider_mgr.get_current_provider_id()
        system_prompt = self._config.get_system_prompt(provider_id)

        # 追加知识库内容
        kb_content = self._build_knowledge_context()
        if kb_content:
            system_prompt += "\n\n" + kb_content

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self._history)

        self._worker = AIResponseWorker(self._provider_mgr, messages)
        self._worker.chunk_received.connect(self._on_ai_chunk)
        self._worker.finished.connect(self._on_ai_finished)
        self._worker.error.connect(self._on_ai_error)
        self._worker.start()

        self.send_btn.setEnabled(False)
        self.send_btn.setText("回复中...")

    def _on_ai_chunk(self, chunk):
        """收到 AI 回复片段（使用节流机制，避免高频渲染）"""
        self._current_response += chunk
        if self._current_stream_bubble and not self._render_pending:
            self._render_pending = True
            self._render_timer.start(50)  # 50ms 内合并多次更新

    def _flush_render(self):
        """执行实际的渲染更新（节流定时器到期）"""
        self._render_pending = False
        if self._current_stream_bubble:
            self._current_stream_bubble.update_content(self._current_response)
            self._scroll_to_bottom()

    def _on_ai_finished(self):
        """AI 回复完成"""
        # 强制刷新最后一次渲染
        self._render_timer.stop()
        self._flush_render()
        if self._current_stream_bubble:
            self._current_stream_bubble.set_streaming(False)
        self._history.append({"role": "assistant", "content": self._current_response})
        self._enforce_history_cap()
        self._cleanup_worker()

    def _on_clear_context(self):
        """清空对话历史和上下文"""
        self._history.clear()
        # 清除消息区域中除欢迎消息外的所有气泡
        while self.msg_layout.count() > 1:
            item = self.msg_layout.takeAt(1)
            if item and item.widget():
                item.widget().deleteLater()
        # 重新添加欢迎消息（如果已不在则跳过）
        if self.msg_layout.count() == 0:
            self._add_welcome_message()
        # 清空输入框
        self.input_edit.clear()
        # 使知识库缓存失效（下次发送时重新加载）
        invalidate_cache()
        logger.info("对话上下文已清空")

    def _on_ai_error(self, error_msg):
        """AI 回复出错"""
        self._render_timer.stop()
        self._render_pending = False
        err_text = f"\n\n**请求出错**: {error_msg}"
        if self._current_stream_bubble:
            self._current_stream_bubble.update_content(self._current_response + err_text)
            self._current_stream_bubble.set_streaming(False)
        self._cleanup_worker()

    def _enforce_history_cap(self):
        """限制历史对话长度，超出时丢弃最早的对话对"""
        while len(self._history) > self.MAX_HISTORY_PAIRS * 2:
            # 丢弃最早的一对 (user, assistant) 消息
            removed = 0
            for i, msg in enumerate(self._history):
                if msg["role"] == "user":
                    # 移除这条 user 消息和下一条 assistant 消息
                    self._history.pop(i)
                    if i < len(self._history) and self._history[i]["role"] == "assistant":
                        self._history.pop(i)
                    removed = 2
                    break
            if removed == 0:
                break  # 防止无限循环

    def _build_knowledge_context(self):
        """加载知识库内容，追加到系统提示词末尾"""
        enabled = self._config.get("knowledge_base.enabled", False)
        if not enabled:
            return ""
        kb_path = self._config.get("knowledge_base.path", "")
        return load_knowledge_base(kb_path if kb_path else None)

    def _cleanup_worker(self):
        """清理工作线程状态"""
        self._worker = None
        self._current_stream_bubble = None
        self._current_response = ""
        self.send_btn.setEnabled(True)
        self.send_btn.setText("发送")
        self._scroll_to_bottom()

    def _add_message(self, role, content, is_streaming=False, is_welcome=False):
        """
        在消息区域添加一条消息

        参数:
            role: "user" 或 "assistant"
            content: str - 消息内容
            is_streaming: bool - 是否流式输出
            is_welcome: bool - 是否欢迎消息（不加入历史）
        """
        bubble = MessageBubble(role, content, is_streaming)
        self.msg_layout.addWidget(bubble)

        if not is_welcome:
            QTimer.singleShot(50, self._scroll_to_bottom)

        return bubble

    def _scroll_to_bottom(self):
        """滚动消息区域到底部"""
        scrollbar = self.scroll_area.verticalScrollBar()
        if scrollbar:
            scrollbar.setValue(scrollbar.maximum())

    def append_screenshot(self, base64_image):
        """处理截图结果（由主程序调用）"""
        text = self.input_edit.toPlainText().strip()
        if not text:
            text = "请分析这张图片"
        self.input_edit.clear()
        self._add_message("user", f"[截图] {text}")
        self._history.append({"role": "user", "content": f"[截图] {text}"})

        # 获取系统提示词
        provider_id = self._provider_mgr.get_current_provider_id()
        system_prompt = self._config.get_system_prompt(provider_id)

        # 追加知识库内容
        kb_content = self._build_knowledge_context()
        if kb_content:
            system_prompt += "\n\n" + kb_content

        # 启动 AI 视觉分析
        self._current_response = ""
        self._current_stream_bubble = self._add_message("assistant", "", is_streaming=True)

        adapter = self._provider_mgr.get_current_adapter()
        if adapter and adapter.supports_images:
            # 构建多模态消息
            image_messages = AIAdapter.build_image_message(text, base64_image)
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(self._history[:-1])  # 排除刚加的 user 消息，用图片消息替代
            messages.extend(image_messages)
        else:
            # 不支持图片的模型，只发送文字描述
            prompt = f"用户截取了一张图片，描述为: {text}。请根据此描述提供帮助。"
            messages = [{"role": "system", "content": system_prompt}]
            self._history[-1] = {"role": "user", "content": prompt}
            messages.extend(self._history)

        # 启动 AI 工作线程
        self._worker = AIResponseWorker(self._provider_mgr, messages)
        self._worker.chunk_received.connect(self._on_ai_chunk)
        self._worker.finished.connect(self._on_ai_finished)
        self._worker.error.connect(self._on_ai_error)
        self._worker.start()

        self.send_btn.setEnabled(False)
        self.send_btn.setText("回复中...")

    def append_text(self, text):
        """处理文字选取结果（由主程序调用）"""
        self.input_edit.setPlainText(text)
        # 自动发送
        self._on_send_message()

    def update_model_label(self, provider_id):
        """更新模型标签"""
        provider = self._config.get_provider_by_id(provider_id)
        if provider:
            model_text = f"{provider['name']} - {provider.get('model', '')}"
            self.model_label.setText(f"模型: {model_text}")
            self.title_bar.set_title(f"AI 助手 - {provider['name']}")

    def showEvent(self, event):
        """窗口显示时恢复位置和大小"""
        super().showEvent(event)
        # 使用 QTimer 确保窗口已完全显示后再设置位置
        QTimer.singleShot(0, self._restore_geometry)

    def _restore_geometry(self):
        """从配置恢复窗口位置和大小"""
        # 大小
        cfg = self._config.get("chat_window", {})
        width = cfg.get("width", 600)
        height = cfg.get("height", 520)

        # 确保最小尺寸
        width = max(width, self.MIN_WIDTH)
        height = max(height, self.MIN_HEIGHT)

        self.resize(width, height)

        # 位置
        pos_x = cfg.get("pos_x")
        pos_y = cfg.get("pos_y")
        if pos_x is not None and pos_y is not None:
            self.move(pos_x, pos_y)
        else:
            # 默认居中
            screen = self.screen()
            if screen:
                geo = screen.availableGeometry()
                self.move(
                    geo.x() + (geo.width() - width) // 2,
                    geo.y() + (geo.height() - height) // 2
                )

        # 透明度
        opacity = cfg.get("opacity", 0.92)
        self.setWindowOpacity(opacity)
        slider_val = int(opacity * 100)
        self.opacity_slider.setValue(slider_val)

    def resizeEvent(self, event):
        """窗口大小变化时保存配置、更新消息宽度、控制模型标签显示"""
        super().resizeEvent(event)
        # 保存大小
        self._config.set("chat_window.width", self.width())
        self._config.set("chat_window.height", self.height())

        # 更新拖拽手柄位置
        if hasattr(self, 'size_grip'):
            self.size_grip.move(
                self.width() - self.size_grip.width() - 2,
                self.height() - self.size_grip.height() - 2
            )

        # 窗口过窄时隐藏模型名称标签以减小最小宽度限制
        if hasattr(self, 'model_label'):
            if self.width() < self.MODEL_LABEL_HIDE_WIDTH:
                self.model_label.hide()
            else:
                self.model_label.show()

        # 消息气泡通过自身的 resizeEvent 自动适配宽度和换行

    def _update_message_widths(self):
        """消息气泡通过自身的 resizeEvent 自动适配，无需手动调整"""

    def moveEvent(self, event):
        """窗口移动时保存位置"""
        super().moveEvent(event)
        self._config.set("chat_window.pos_x", self.pos().x())
        self._config.set("chat_window.pos_y", self.pos().y())

    def nativeEvent(self, eventType, message):
        """处理 WM_NCHITTEST 实现边缘拖拽缩放（无边框窗口保留原生缩放行为）"""
        if eventType == b"windows_generic_MSG":
            try:
                import ctypes
                from ctypes import wintypes
                msg = ctypes.wintypes.MSG.from_address(int(message))
            except (ValueError, TypeError):
                return super().nativeEvent(eventType, message)

            if msg.message == 0x0084:  # WM_NCHITTEST
                # QCursor.pos() 返回 Qt 逻辑坐标（自动处理 DPI 缩放）
                local = self.mapFromGlobal(QCursor.pos())
                margin = self.RESIZE_MARGIN
                w, h = self.width(), self.height()

                # 标题栏区域（36px）不做缩放，让 TitleBar 自行处理拖动
                if local.y() <= self.title_bar.height():
                    return (True, 1)   # HTCLIENT

                on_left   = local.x() <= margin
                on_right  = local.x() >= w - margin
                on_top    = local.y() <= margin
                on_bottom = local.y() >= h - margin

                # HT 常量
                HTLEFT, HTRIGHT = 10, 11
                HTTOP, HTTOPLEFT, HTTOPRIGHT = 12, 13, 14
                HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 15, 16, 17
                HTCLIENT = 1

                # 右下角保留给 QSizeGrip（18px 区域）
                if on_bottom and on_right and local.x() >= w - 18 and local.y() >= h - 18:
                    return (True, HTCLIENT)

                if on_top and on_left:    return (True, HTTOPLEFT)
                if on_top and on_right:   return (True, HTTOPRIGHT)
                if on_bottom and on_left:  return (True, HTBOTTOMLEFT)
                if on_bottom and on_right: return (True, HTBOTTOMRIGHT)
                if on_top:    return (True, HTTOP)
                if on_bottom: return (True, HTBOTTOM)
                if on_left:   return (True, HTLEFT)
                if on_right:  return (True, HTRIGHT)

                return (True, HTCLIENT)

        return super().nativeEvent(eventType, message)

    def keyPressEvent(self, event):
        """全局快捷键：Esc 快速隐藏窗口"""
        if event.key() == Qt.Key_Escape:
            self.hide()
            self.window_hidden.emit()
        else:
            super().keyPressEvent(event)

    def eventFilter(self, obj, event):
        """事件过滤器：Ctrl+Enter 发送，Esc 隐藏"""
        if obj is self.input_edit and event.type() == event.Type.KeyPress:
            if event.key() == Qt.Key_Return and event.modifiers() & Qt.ControlModifier:
                self._on_send_message()
                return True
            if event.key() == Qt.Key_Escape:
                self.hide()
                self.window_hidden.emit()
                return True
        return super().eventFilter(obj, event)

    def _load_config(self):
        """加载配置"""
        # 透明度
        opacity = self._config.get("chat_window.opacity", 0.92)
        self.setWindowOpacity(opacity)
        self.opacity_slider.setValue(int(opacity * 100))

    def _apply_style(self):
        """应用样式表"""
        self.setStyleSheet("""
            ChatWindow {
                background-color: #2b2b2b;
                border: 1px solid #444;
            }
            #controlBar {
                background-color: #333;
                border-bottom: 1px solid #444;
            }
            #controlBar QLabel {
                color: #aaa;
                font-size: 11px;
            }
            #modelLabel {
                color: #4fc3f7;
                font-size: 12px;
                font-weight: bold;
            }
            #messagesContainer {
                background-color: #2b2b2b;
            }
            #inputArea {
                background-color: #333;
                border-top: 1px solid #444;
            }
            QTextEdit {
                background-color: #3c3c3c;
                color: #e0e0e0;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 13px;
            }
            QTextEdit:focus {
                border-color: #0078d4;
            }
            QPushButton#sendBtn {
                background-color: #0078d4;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton#sendBtn:hover {
                background-color: #1a8ae8;
            }
            QPushButton#sendBtn:disabled {
                background-color: #555;
                color: #888;
            }
            QPushButton#clearCtxBtn {
                background-color: transparent;
                color: #888;
                border: 1px solid #555;
                border-radius: 3px;
                font-size: 11px;
                padding: 0 8px;
            }
            QPushButton#clearCtxBtn:hover {
                background-color: #444;
                color: #e0e0e0;
                border-color: #888;
            }
            QSlider::groove:horizontal {
                height: 4px;
                background: #555;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                width: 12px;
                height: 12px;
                margin: -4px 0;
                background: #0078d4;
                border-radius: 6px;
            }
            QSlider::sub-page:horizontal {
                background: #0078d4;
                border-radius: 2px;
            }
            QScrollArea {
                border: none;
                background-color: #2b2b2b;
            }
            QScrollBar:vertical {
                width: 6px;
                background: #2b2b2b;
            }
            QScrollBar::handle:vertical {
                background: #555;
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)
        # 标题栏样式
        self.title_bar.setStyleSheet("""
            TitleBar {
                background-color: #1e1e1e;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QLabel#titleLabel {
                color: #e0e0e0;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton#titleBtn {
                background-color: transparent;
                color: #aaa;
                border: none;
                border-radius: 3px;
                font-size: 14px;
            }
            QPushButton#titleBtn:hover {
                background-color: #444;
                color: white;
            }
            QPushButton#titleBtnClose {
                background-color: transparent;
                color: #aaa;
                border: none;
                border-radius: 3px;
                font-size: 14px;
            }
            QPushButton#titleBtnClose:hover {
                background-color: #c42b1c;
                color: white;
            }
        """)

    def closeEvent(self, event):
        """关闭事件 - 隐藏到系统托盘而非退出"""
        # 隐藏时刷入待保存的配置（位置、大小等）
        self._config.flush()
        event.ignore()
        self.hide()
        self.window_hidden.emit()
