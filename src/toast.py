"""
简易 Toast 通知 - 屏幕中央短暂显示提示信息
"""
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont


class ToastNotification(QWidget):
    """屏幕顶部居中显示的临时通知，自动消失"""

    def __init__(self, text, duration_ms=1500, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.X11BypassWindowManagerHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 12, 24, 12)

        self.label = QLabel(text)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 16px;
                font-weight: bold;
                background-color: rgba(0, 0, 0, 200);
                border-radius: 8px;
                padding: 12px 24px;
            }
        """)
        layout.addWidget(self.label)

        self.adjustSize()
        self._center_on_screen()

        self.show()  # 立即显示

        # 自动消失
        QTimer.singleShot(duration_ms, self.close)

    def _center_on_screen(self):
        screen = self.screen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + geo.height() // 3
            self.move(x, y)

    def closeEvent(self, event):
        super().closeEvent(event)
