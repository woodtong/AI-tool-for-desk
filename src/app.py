"""
AI 桌面助手 - 应用主类
整合所有组件：全局热键、搜索条幅、截图、文字选取、AI 对话
"""
import sys
import os
import logging

from PySide6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QMessageBox,
    QInputDialog, QLineEdit
)
from PySide6.QtCore import Qt, QTimer, QRect
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QAction, QFont

from src.config_manager import ConfigManager
from src.hotkey_manager import HotkeyManager
from src.banner import BannerWindow
from src.chat_window import ChatWindow
from src.screenshot import capture_fullscreen, scale_for_display, get_screen_dpr, capture_region, pixmap_to_base64
from src.screenshot_overlay import ScreenshotOverlay
from src.text_capture import capture_selected_text
from src.ai_providers.manager import AIProviderManager
from src.toast import ToastNotification

logger = logging.getLogger(__name__)


class AIAssistantApp:
    """
    主应用类 - 协调所有组件

    使用流程:
        1. 初始化配置、AI 管理器、热键管理器
        2. 创建搜索条幅、对话窗口、系统托盘
        3. 注册全局快捷键
        4. 根据是否首次运行决定显示策略
    """

    # 默认快捷键（可在 config.json 中覆盖）
    DEFAULT_HOTKEYS = {
        "show_banner":  {"mod": "win+shift", "key": "f"},
        "screenshot":   {"mod": "win+shift", "key": "z"},
        "text_capture": {"mod": "win+shift", "key": "x"},
    }

    def __init__(self):
        # ====== 配置 ======
        self.config = ConfigManager()

        # ====== AI 管理器 ======
        self.ai_manager = AIProviderManager(self.config)

        # ====== 全局热键管理器 ======
        self.hotkey_mgr = HotkeyManager()

        # ====== 截图相关状态 ======
        self._screenshot_pixmap = None
        self._screenshot_overlay = None

        # ====== 搜索条幅 ======
        providers = self.config.get_providers()
        self.banner = BannerWindow(providers)
        self.banner.provider_selected.connect(self._on_provider_selected)
        self.banner.dismissed.connect(self._on_banner_dismissed)

        # ====== 对话窗口 ======
        self.chat = ChatWindow(self.ai_manager, self.config)
        self.chat.window_hidden.connect(self._on_chat_hidden)

        # ====== 系统托盘 ======
        self._setup_tray()

        # ====== 注册热键 ======
        self._register_hotkeys()

        # ====== 初始化状态 ======
        self._check_first_run()

        logger.info("AI 桌面助手初始化完成")

    # ==================== 初始化辅助方法 ====================

    def _setup_tray(self):
        """创建系统托盘图标（写入临时文件确保图标格式正确）"""
        self.tray_icon = QSystemTrayIcon()
        self.tray_icon.setToolTip("AI 桌面助手")

        # 创建程序图标 — 写入临时 PNG 文件再加载，确保 Windows 识别
        import tempfile, os
        icon_pixmap = QPixmap(64, 64)
        icon_pixmap.fill(Qt.transparent)
        painter = QPainter(icon_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(0, 120, 212))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(4, 4, 56, 56, 12, 12)
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Segoe UI", 22, QFont.Bold)
        painter.setFont(font)
        painter.drawText(icon_pixmap.rect(), Qt.AlignCenter, "AI")
        painter.end()
        # 保存到临时文件
        icon_path = os.path.join(tempfile.gettempdir(), "ai_desk_icon.png")
        icon_pixmap.save(icon_path, "PNG")
        app_icon = QIcon(icon_path)
        self.tray_icon.setIcon(app_icon)
        QApplication.instance().setWindowIcon(app_icon)
        logger.debug("托盘图标文件: %s", icon_path)

        # 右键菜单（实例变量，防止 GC）
        self._tray_menu = QMenu()
        self._tray_actions = []

        menu_items = [
            ("显示/隐藏 对话窗口", self._toggle_chat),
            ("选择 AI 模型...", self._show_banner),
            None,  # separator
            ("设置（API Key / 系统提示词）...", self._show_config_dialog),
            None,  # separator
            ("退出", self._quit_app),
        ]
        for item in menu_items:
            if item is None:
                self._tray_menu.addSeparator()
            else:
                label, slot = item
                act = QAction(label, None)
                act.triggered.connect(slot)
                self._tray_menu.addAction(act)
                self._tray_actions.append(act)

        self.tray_icon.setContextMenu(self._tray_menu)

        # activated 信号 — 直接用 Qt.DirectConnection
        self.tray_icon.activated.connect(self._on_tray_activated)

        # 发送一条初始化通知以"注册"托盘图标到 Windows Shell
        self.tray_icon.show()
        QTimer.singleShot(100, lambda: self.tray_icon.showMessage(
            "AI 桌面助手", "程序已启动，点击图标切换窗口", QSystemTrayIcon.Information, 2000
        ))

    def _register_hotkeys(self):
        """注册全局快捷键"""
        hotkey_cfg = self.config.get("hotkeys", {})

        registered = 0
        failed_list = []
        action_methods = {
            "show_banner": ("唤出条幅", "_show_banner"),
            "screenshot": ("截图", "_start_screenshot"),
            "text_capture": ("文字选取", "_start_text_capture"),
        }
        for action_name, default in self.DEFAULT_HOTKEYS.items():
            cfg = hotkey_cfg.get(action_name, default)
            mod_str = cfg.get("mod", default["mod"])
            key_str = cfg.get("key", default["key"])
            label, method_name = action_methods[action_name]
            hid = self.hotkey_mgr.register(
                mod_str, key_str,
                getattr(self, method_name)
            )
            if hid is not None:
                registered += 1
            else:
                failed_list.append("%s (%s+%s)" % (label, mod_str, key_str))

        # 将热键过滤器安装到应用
        QApplication.instance().installNativeEventFilter(self.hotkey_mgr)
        logger.info("热键注册完成: %d/3 成功", registered)
        if failed_list:
            fail_text = "\n".join("- " + f for f in failed_list)
            self.chat._add_message("assistant",
                "⚠️ **快捷键注册失败**\n\n"
                "以下快捷键注册失败（请检查是否被其他程序占用）:\n%s\n\n"
                "请关闭占用程序后重启本应用，"
                "或修改 `config.json` 中的 `hotkeys` 项更换快捷键。" % fail_text
            )

    def _check_first_run(self):
        """检查是否首次运行"""
        if self.config.get("first_run", True):
            QTimer.singleShot(500, self._show_banner)
            self.config.mark_first_run_done()
            logger.info("首次运行，显示搜索条幅")
        else:
            self.chat.show()

    # ==================== 热键回调 ====================

    def _show_banner(self):
        """显示搜索条幅"""
        providers = self.config.get_providers()
        self.banner.update_providers(providers)
        self.banner.show()
        self.banner.raise_()
        self.banner.activateWindow()

    def _start_screenshot(self):
        """开始截图流程"""
        try:
            ToastNotification("📸 截图模式 — 拖拽选择区域，Esc 取消", 1200)
            self.chat.hide()
            QTimer.singleShot(200, self._do_screenshot)
            logger.debug("截图热键触发")
        except Exception as e:
            ToastNotification(f"⚠️ 截图启动失败: {e}", 2500)
            logger.error("截图启动失败: %s", e, exc_info=True)

    def _do_screenshot(self):
        """执行截图（保留物理分辨率用于裁剪，缩放后用于显示）"""
        try:
            # 捕获原始物理分辨率截图
            phys_pixmap = capture_fullscreen()
            self._screenshot_pixmap = phys_pixmap
            # 计算 DPI 缩放比，用于坐标转换
            self._screenshot_dpr = get_screen_dpr(phys_pixmap)

            # 缩放到逻辑分辨率用于遮罩层显示
            display_pixmap = scale_for_display(phys_pixmap)
        except Exception as e:
            ToastNotification(f"⚠️ 截图失败: {e}", 2500)
            logger.error("截图失败: %s", e, exc_info=True)
            self.chat.show()
            return

        self._screenshot_overlay = ScreenshotOverlay(display_pixmap)
        self._screenshot_overlay.region_selected.connect(self._on_region_selected)
        self._screenshot_overlay.canceled.connect(self._on_screenshot_canceled)
        self._screenshot_overlay.show()
        self._screenshot_overlay.raise_()
        self._screenshot_overlay.activateWindow()

    def _on_region_selected(self, rect):
        """截图区域选中回调"""
        try:
            # 从物理分辨率截图裁剪，确保最大清晰度
            dpr = getattr(self, '_screenshot_dpr', 1.0)
            if dpr != 1.0:
                full_rect = QRect(
                    int(round(rect.x() * dpr)),
                    int(round(rect.y() * dpr)),
                    int(round(rect.width() * dpr)),
                    int(round(rect.height() * dpr))
                )
            else:
                full_rect = rect

            # 确保不超出截图边界
            pw = self._screenshot_pixmap.width()
            ph = self._screenshot_pixmap.height()
            full_rect = full_rect.intersected(QRect(0, 0, pw, ph))

            region_pixmap = self._screenshot_pixmap.copy(full_rect)
            b64 = pixmap_to_base64(region_pixmap)

            QTimer.singleShot(100, self.chat.show)
            self.chat.append_screenshot(b64)
        except Exception as e:
            logger.error("截图选区处理失败: %s", e, exc_info=True)
            ToastNotification(f"⚠️ 截图处理失败: {e}", 2500)
            QTimer.singleShot(100, self.chat.show)
        finally:
            self._screenshot_overlay = None
            self._screenshot_pixmap = None
            self._screenshot_dpr = None

    def _on_screenshot_canceled(self):
        """截图取消回调"""
        self._screenshot_overlay = None
        self._screenshot_pixmap = None
        self._screenshot_dpr = None
        QTimer.singleShot(100, self.chat.show)

    def _start_text_capture(self):
        """开始文字选取"""
        try:
            logger.debug("文字选取热键触发")
            # 不做任何窗口操作（避免改变前台窗口焦点），静默复制
            capture_selected_text(self._on_text_captured)
        except Exception as e:
            ToastNotification(f"⚠️ 文字选取失败: {e}", 2500)
            logger.error("文字选取失败: %s", e, exc_info=True)

    def _on_text_captured(self, text):
        """文字选取完成回调"""
        if text.strip():
            self.chat.show()
            self.chat.raise_()
            self.chat.activateWindow()
            self.chat.append_text(text)
        else:
            ToastNotification("⚠️ 未检测到选中文字，请先选中内容再按快捷键", 2000)
            self.chat.show()

    # ==================== 信号处理 ====================

    def _on_provider_selected(self, provider_id):
        """AI 模型被选中"""
        self.ai_manager.set_current(provider_id)
        self.chat.update_model_label(provider_id)
        self.chat.show()
        self.chat.raise_()
        self.chat.activateWindow()
        logger.info("已选择 AI 模型: %s", provider_id)

    def _on_banner_dismissed(self):
        """搜索条幅被关闭"""
        if not self.chat.isVisible() and self.ai_manager.get_current_adapter():
            self.chat.show()

    def _on_chat_hidden(self):
        """对话窗口被隐藏（关闭按钮）"""

    def _toggle_chat(self):
        """切换对话窗口显示状态"""
        if self.chat.isVisible():
            self.chat.hide()
        else:
            self.chat.show()
            self.chat.raise_()
            self.chat.activateWindow()

    def _on_tray_activated(self, reason):
        """托盘图标点击处理"""
        # 记录原因值，方便诊断
        reason_map = {0: "Unknown", 1: "Context", 2: "DoubleClick", 3: "Trigger", 4: "MiddleClick"}
        logger.debug("托盘图标 activated: reason=%d (%s)", reason, reason_map.get(reason, "?"))

        if reason == QSystemTrayIcon.Context:
            # 右键 — 弹出菜单（setContextMenu 在 Win11 上不可靠，手动弹出）
            if hasattr(self, '_tray_menu') and self._tray_menu:
                from PySide6.QtGui import QCursor
                self._tray_menu.exec(QCursor.pos())
        elif reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger):
            self._toggle_chat()
        elif reason == QSystemTrayIcon.Unknown:
            # Unknown 在某些 Win11 + PySide6 版本上代表左键
            self._toggle_chat()

    def _show_config_dialog(self):
        """显示完整设置对话框（API Key + 系统提示词 + 知识库）"""
        from PySide6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
            QGroupBox, QPushButton, QLineEdit, QCheckBox, QScrollArea,
            QWidget
        )

        dialog = QDialog(None)
        dialog.setWindowTitle("AI 桌面助手 - 设置")
        dialog.resize(520, 420)
        dialog.setMinimumSize(400, 300)
        dialog.setStyleSheet("""
            QDialog { background-color: #2b2b2b; color: #e0e0e0; }
            QScrollArea { border: none; background: transparent; }
            QGroupBox {
                border: 1px solid #444; border-radius: 6px;
                margin-top: 14px; padding: 14px; padding-top: 22px;
                font-weight: bold; color: #4fc3f7;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 2px 8px;
            }
            QLabel { color: #ccc; font-size: 13px; }
            QTextEdit, QLineEdit {
                background-color: #3c3c3c; color: #e0e0e0;
                border: 1px solid #555; border-radius: 4px;
                padding: 6px; font-size: 13px;
            }
            QPushButton {
                background-color: #0078d4; color: white;
                border: none; border-radius: 4px;
                padding: 8px 24px; font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background-color: #1a8ae8; }
        """)

        # ====== 外层布局：滚动内容 + 底部固定按钮 ======
        outer_layout = QVBoxLayout(dialog)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # ====== 可滚动的内容区域 ======
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        main_layout = QVBoxLayout(content)
        main_layout.setContentsMargins(12, 8, 12, 8)
        main_layout.setSpacing(6)

        # ----- 全局系统提示词 -----
        global_group = QGroupBox("全局系统提示词（所有模型共用）")
        gl_layout = QVBoxLayout(global_group)
        global_edit = QTextEdit()
        global_edit.setPlainText(self.config.get("system_prompt", ""))
        global_edit.setPlaceholderText("输入全局系统提示词...")
        global_edit.setMaximumHeight(80)
        gl_layout.addWidget(global_edit)
        main_layout.addWidget(global_group)

        # ----- 知识库设置 -----
        kb_group = QGroupBox("知识库（文件作为 AI 上下文参考）")
        kb_form = QVBoxLayout(kb_group)
        kb_form.setSpacing(4)

        self._kb_enabled_cb = QCheckBox("启用知识库")
        self._kb_enabled_cb.setChecked(self.config.get("knowledge_base.enabled", False))
        kb_form.addWidget(self._kb_enabled_cb)

        kb_path_layout = QHBoxLayout()
        kb_path_layout.addWidget(QLabel("知识库路径:"))
        self._kb_path_edit = QLineEdit()
        self._kb_path_edit.setText(self.config.get("knowledge_base.path", ""))
        self._kb_path_edit.setPlaceholderText("留空则使用默认路径 (knowledge_base/)")
        kb_path_layout.addWidget(self._kb_path_edit, 1)
        kb_form.addLayout(kb_path_layout)

        kb_info = QLabel("💡 将 .txt / .md / .py 等文件放入知识库文件夹，AI 自动读取作为上下文。\n"
                         "支持的文件类型和限制请查看 knowledge_base/README.md")
        kb_info.setStyleSheet("color: #888; font-size: 11px; padding: 4px 0;")
        kb_info.setWordWrap(True)
        kb_form.addWidget(kb_info)
        main_layout.addWidget(kb_group)

        # ----- 各模型设置 -----
        providers = self.config.get_providers()
        provider_edits = {}

        for p in providers:
            name = f"{p['name']}" + (f" - {p['model']}" if p.get('model') else "")
            group = QGroupBox(name)
            form = QVBoxLayout(group)
            form.setSpacing(4)

            key_layout = QHBoxLayout()
            key_layout.addWidget(QLabel("API Key:"))
            key_edit = QLineEdit()
            key_edit.setEchoMode(QLineEdit.Password)
            key_edit.setText(p.get("api_key", ""))
            key_layout.addWidget(key_edit, 1)
            form.addLayout(key_layout)

            form.addWidget(QLabel("模型专属提示词（可选，与全局提示词拼接）:"))
            prompt_edit = QTextEdit()
            prompt_edit.setPlainText(p.get("system_prompt", ""))
            prompt_edit.setPlaceholderText("留空则使用全局系统提示词")
            prompt_edit.setMaximumHeight(60)
            form.addWidget(prompt_edit)

            provider_edits[p["id"]] = {"key": key_edit, "prompt": prompt_edit}
            main_layout.addWidget(group)

        # 底部留白
        main_layout.addStretch()

        scroll.setWidget(content)
        outer_layout.addWidget(scroll, 1)

        # ====== 底部固定按钮 ======
        btn_bar = QWidget()
        btn_layout = QHBoxLayout(btn_bar)
        btn_layout.setContentsMargins(12, 8, 12, 8)
        btn_layout.addStretch()

        save_btn = QPushButton("保存")
        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet("QPushButton { background-color: #555; } "
                                  "QPushButton:hover { background-color: #666; }")

        def on_save():
            self.config.set_global_system_prompt(global_edit.toPlainText())
            self.config.set("knowledge_base.enabled", self._kb_enabled_cb.isChecked())
            self.config.set("knowledge_base.path", self._kb_path_edit.text())
            for pid, edits in provider_edits.items():
                self.config.update_provider(pid, {
                    "api_key": edits["key"].text(),
                    "system_prompt": edits["prompt"].toPlainText(),
                })
                self.ai_manager._adapters.pop(pid, None)
            dialog.accept()

        save_btn.clicked.connect(on_save)
        cancel_btn.clicked.connect(dialog.reject)

        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        outer_layout.addWidget(btn_bar)

        dialog.exec()

    def _quit_app(self):
        """退出程序"""
        self.hotkey_mgr.unregister_all()
        QApplication.instance().removeNativeEventFilter(self.hotkey_mgr)

        self.config.set("chat_window.pos_x", self.chat.pos().x())
        self.config.set("chat_window.pos_y", self.chat.pos().y())
        self.config.set("chat_window.width", self.chat.width())
        self.config.set("chat_window.height", self.chat.height())

        QApplication.quit()
        logger.info("AI 桌面助手已退出")


def _check_single_instance():
    """使用 Windows 命名 Mutex 检查是否已有实例在运行"""
    import ctypes
    from ctypes import wintypes
    # 使用基于项目路径的哈希值来生成唯一互斥体名
    import hashlib
    project_hash = hashlib.md5(__file__.encode("utf-8")).hexdigest()[:12]
    MUTEX_NAME = "Local\\AIToolForDesk_%s" % project_hash
    ERROR_ALREADY_EXISTS = 183

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE

    mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not mutex:
        return True  # 无法创建mutex，还是继续运行

    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        logger.warning("检测到已有实例在运行 (mutex=%s)", MUTEX_NAME)
        # 尝试激活已有窗口
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.FindWindowW(None, "AI 助手")
            if hwnd:
                user32.SetForegroundWindow(hwnd)
                user32.ShowWindow(hwnd, 5)  # SW_SHOW
        except Exception:
            pass
        return False

    return True  # 唯一实例，继续


def _install_ctrl_c_handler(app):
    """安装 Ctrl+C 信号处理器，让 PySide6 应用能响应 Ctrl+C 退出"""
    import signal
    sigint_count = [0]

    def sigint_handler(signum, frame):
        sigint_count[0] += 1
        if sigint_count[0] >= 2:
            logger.warning("强制退出")
            sys.exit(1)
        logger.warning("检测到 Ctrl+C，正在退出... (再次按 Ctrl+C 强制退出)")
        app.quit()

    signal.signal(signal.SIGINT, sigint_handler)

    # 每 500ms 超时一次，让 Python 有机会处理待处理的 SIGINT
    timer = QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(500)
    return timer


def main():
    """主函数 - 应用入口"""
    # 单实例检查
    if not _check_single_instance():
        logger.warning("AI 桌面助手已在运行，退出当前实例")
        sys.exit(0)

    # 高 DPI 支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("AI 桌面助手")
    app.setOrganizationName("AITool")
    # 关闭最后一个窗口时不要退出（系统托盘需要）
    app.setQuitOnLastWindowClosed(False)

    # 安装 Ctrl+C 处理器（保持引用防止 GC）
    _ctrl_c_timer = _install_ctrl_c_handler(app)

    # 创建主应用实例
    assistant = AIAssistantApp()

    # 运行事件循环
    sys.exit(app.exec())
