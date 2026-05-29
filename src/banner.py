"""
搜索条幅窗口 - 屏幕顶部的小型搜索栏
- 右侧下拉列表选择 AI 模型
- 输入框可搜索过滤 AI 模型名称
- 选中后自动隐藏，通过快捷键再次唤出
"""
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLineEdit, QComboBox,
    QLabel, QPushButton, QCompleter
)
from PySide6.QtCore import Qt, Signal, QTimer, QStringListModel
from PySide6.QtGui import QIcon


class SearchableComboBox(QComboBox):
    """
    可搜索过滤的下拉框
    输入文字时自动过滤匹配项
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.placeholderText()
        # 存储所有原始项
        self._all_items = []

        # 输入框文字变化时触发过滤
        self.lineEdit().textEdited.connect(self._on_text_edited)

    def addItem(self, text, userData=None):
        """重写 addItem，保存原始项列表"""
        self._all_items.append((text, userData))
        super().addItem(text, userData)

    def clear(self):
        """重写 clear"""
        self._all_items.clear()
        super().clear()

    def _restore_all_items(self):
        """恢复下拉框显示完整的 _all_items 列表（不影响 _all_items 自身）"""
        self.blockSignals(True)
        text = self.currentText()
        super().clear()          # 只清 combo 显示，不清 _all_items
        for item_text, item_data in self._all_items:
            super().addItem(item_text, item_data)
        self.setEditText(text)
        self.blockSignals(False)

    def _on_text_edited(self, text):
        """输入文字变化时过滤下拉列表（不修改 _all_items）"""
        current = self.currentText()

        self.blockSignals(True)
        super().clear()          # 只清 combo 显示，保留 _all_items

        if not text.strip():
            # 无过滤条件时显示全部
            for item_text, item_data in self._all_items:
                super().addItem(item_text, item_data)
        else:
            # 按文字匹配过滤
            for item_text, item_data in self._all_items:
                if text.lower() in item_text.lower():
                    super().addItem(item_text, item_data)

        self.setEditText(current)
        self.blockSignals(False)

        # 过滤结果供用户通过 ▼ 按钮查看，不自动弹出（避免打断输入）
        # 用户输入后按 Enter 即可确认选择第一个匹配项

    def set_placeholder(self, text):
        """设置占位提示文字"""
        self.lineEdit().setPlaceholderText(text)


class BannerWindow(QWidget):
    """
    搜索条幅窗口 - 位于屏幕顶部的 AI 模型选择栏
    信号:
        provider_selected(provider_id: str): 用户选择了一个 AI 模型
        dismissed(): 用户关闭了条幅
    """

    provider_selected = Signal(str)
    dismissed = Signal()

    WIDTH = 500
    HEIGHT = 52

    def __init__(self, providers, parent=None):
        super().__init__(parent)
        # providers: list of dict, 每个包含 id, name, model 等字段
        self._providers = providers
        self._setup_ui()
        self._apply_style()

    def _setup_ui(self):
        """初始化界面"""
        self.setWindowTitle("AI 工具选择")
        # 无边框、置顶、工具窗口
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.X11BypassWindowManagerHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setFixedSize(self.WIDTH, self.HEIGHT)

        # 主布局
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(10)

        # 左侧标签
        label = QLabel("AI 工具:")
        label.setObjectName("bannerLabel")
        layout.addWidget(label)

        # 中间可搜索的下拉框
        self.combo = SearchableComboBox()
        self.combo.setMinimumWidth(300)
        self._populate_combo()
        self.combo.set_placeholder("输入名称搜索或选择 AI 模型...")
        self.combo.setMaxVisibleItems(5)  # 超过5个自动滚动
        layout.addWidget(self.combo, 1)

        # 下拉箭头按钮（指示可下拉选择，点击弹出下拉列表）
        self.dropdown_btn = QPushButton("▼")
        self.dropdown_btn.setObjectName("dropdownBtn")
        self.dropdown_btn.setFixedSize(28, 28)
        self.dropdown_btn.setCursor(Qt.PointingHandCursor)
        self.dropdown_btn.clicked.connect(self._on_dropdown_click)
        layout.addWidget(self.dropdown_btn)

        # 关闭按钮（隐藏，不是退出）
        self.close_btn = QPushButton("×")
        self.close_btn.setObjectName("closeBtn")
        self.close_btn.setFixedSize(28, 28)
        self.close_btn.clicked.connect(self._on_dismiss)
        layout.addWidget(self.close_btn)

        # 回车键确认
        self.combo.lineEdit().returnPressed.connect(self._on_confirm)
        # 下拉选中即确认（无需手动点按钮）
        self.combo.activated.connect(self._on_combo_activated)

    def _populate_combo(self):
        """将 AI 提供者列表填充到下拉框"""
        self.combo.blockSignals(True)
        for p in self._providers:
            display_name = f"{p['name']} - {p['model']}" if p.get('model') else p['name']
            self.combo.addItem(display_name, p.get('id', ''))
        self.combo.blockSignals(False)

    def update_providers(self, providers):
        """更新提供者列表"""
        self._providers = providers
        self.combo.clear()
        self._populate_combo()

    def _on_combo_activated(self, index):
        """下拉列表选中某项时直接确认"""
        provider_id = self.combo.itemData(index)
        if not provider_id:
            return
        self.provider_selected.emit(provider_id)
        self.hide()

    def _on_dropdown_click(self):
        """下拉箭头点击 - 展开完整列表，选择后自动确认"""
        self.combo._restore_all_items()
        self.combo.showPopup()

    def _on_confirm(self):
        """回车确认选择 - 发送信号并隐藏"""
        provider_id = self.combo.currentData()
        if not provider_id:
            # 输入部分文字时，自动选中第一个匹配项
            text = self.combo.currentText()
            for i in range(self.combo.count()):
                if text.lower() in self.combo.itemText(i).lower():
                    provider_id = self.combo.itemData(i)
                    break
        if not provider_id:
            return
        self.provider_selected.emit(provider_id)
        self.hide()

    def _on_dismiss(self):
        """取消/关闭"""
        self.dismissed.emit()
        self.hide()

    def showEvent(self, event):
        """窗口显示时定位到屏幕顶部居中"""
        super().showEvent(event)
        self._center_on_screen()
        # 聚焦到下拉框
        self.combo.setFocus()
        self.combo.lineEdit().selectAll()

    def _center_on_screen(self):
        """将窗口定位到屏幕顶部 1/3 处居中"""
        screen = self.screen()
        if screen:
            geometry = screen.availableGeometry()
            x = geometry.x() + (geometry.width() - self.WIDTH) // 2
            y = geometry.y() + geometry.height() // 4
            self.move(x, y)

    def _apply_style(self):
        """应用样式"""
        self.setStyleSheet("""
            BannerWindow {
                background-color: #2d2d2d;
                border: 1px solid #555;
                border-radius: 8px;
            }
            QLabel#bannerLabel {
                color: #e0e0e0;
                font-size: 14px;
                font-weight: bold;
            }
            QComboBox {
                background-color: #3c3c3c;
                color: #e0e0e0;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 13px;
                min-height: 24px;
            }
            QComboBox:hover {
                border-color: #0078d4;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 28px;
                border-left: 1px solid #555;
            }
            QComboBox QAbstractItemView {
                background-color: #3c3c3c;
                color: #e0e0e0;
                selection-background-color: #0078d4;
                border: 1px solid #555;
                outline: none;
            }
            QLineEdit {
                background-color: #3c3c3c;
                color: #e0e0e0;
                border: none;
                padding: 4px;
            }
            QPushButton#closeBtn {
                background-color: transparent;
                color: #999;
                border: none;
                border-radius: 4px;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton#closeBtn:hover {
                background-color: #c42b1c;
                color: white;
            }
            QPushButton#dropdownBtn {
                background-color: #3c3c3c;
                color: #aaa;
                border: 1px solid #555;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton#dropdownBtn:hover {
                background-color: #4a4a4a;
                color: #fff;
                border-color: #0078d4;
            }
        """)
