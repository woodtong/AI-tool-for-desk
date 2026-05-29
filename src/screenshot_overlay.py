"""
截图遮罩层 - 全屏覆盖，显示当前屏幕截图并允许鼠标框选区域
- 全屏半透明遮罩
- 鼠标拖拽框选（橡皮筋效果）
- Esc 取消
- 松开鼠标确认选区
"""
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, Signal, QRect, QRectF, QPoint
from PySide6.QtGui import QPainter, QPen, QColor, QPixmap, QBrush, QCursor, QFont, QPainterPath


class ScreenshotOverlay(QWidget):
    """
    全屏截图遮罩层，用于框选截图区域
    信号:
        region_selected(QRect): 用户选中的区域（屏幕坐标）
        canceled(): 用户取消截图
    """

    region_selected = Signal(QRect)
    canceled = Signal()

    def __init__(self, screenshot_pixmap=None):
        """
        参数:
            screenshot_pixmap: QPixmap - 全屏截图（取完后传入）
        """
        super().__init__()
        self._pixmap = screenshot_pixmap
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.X11BypassWindowManagerHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        # 鼠标跟踪，实时更新选框
        self.setMouseTracking(True)
        # 十字准星光标，提示用户正在截图
        self.setCursor(QCursor(Qt.CrossCursor))

        # 选框状态
        self._selecting = False
        self._start_pos = QPoint()
        self._current_pos = QPoint()

    def set_screenshot(self, pixmap):
        """设置截图图片"""
        self._pixmap = pixmap
        self.update()

    def showEvent(self, event):
        """显示时铺满整个屏幕"""
        super().showEvent(event)
        if self.screen():
            geo = self.screen().geometry()
            self.setGeometry(geo)
            self.raise_()
            self.activateWindow()

    def paintEvent(self, event):
        """绘制遮罩层"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self._pixmap and not self._pixmap.isNull():
            # 绘制原始截图作为背景
            painter.drawPixmap(0, 0, self._pixmap)

            # 顶部使用说明条（在遮罩层上方，始终保持可见）
            hint_rect = QRect(0, 0, self.width(), 36)
            painter.fillRect(hint_rect, QColor(0, 0, 0, 200))
            painter.setPen(QColor(255, 255, 255))
            hint_font = QFont("Microsoft YaHei", 13)
            painter.setFont(hint_font)
            painter.drawText(hint_rect, Qt.AlignCenter, "🖱️ 拖拽选择截图区域  |  Esc 取消截图  |  松开鼠标确认")

            # 如果有正在选择的区域，用遮罩覆盖除选区外的部分
            if self._selecting or (self._start_pos != self._current_pos):
                sel_rect = self._get_normalized_rect()

                # 使用 QPainterPath + OddEvenFill 实现"挖洞"效果
                # 全屏遮罩覆盖，选区部分留空以显示下方截图
                path = QPainterPath()
                path.addRect(QRectF(self.rect()))
                path.addRect(QRectF(sel_rect))
                path.setFillRule(Qt.OddEvenFill)
                painter.fillPath(path, QColor(0, 0, 0, 160))

                # 绘制选区边框（高亮）
                border_pen = QPen(QColor(0, 120, 212), 2.5)
                painter.setPen(border_pen)
                painter.drawRect(sel_rect)

                # 绘制选区角标（四个角的小矩形）
                handle_color = QColor(0, 120, 212)
                handle_size = 8
                painter.fillRect(sel_rect.x(), sel_rect.y(), handle_size, handle_size, handle_color)
                painter.fillRect(sel_rect.right() - handle_size, sel_rect.y(), handle_size, handle_size, handle_color)
                painter.fillRect(sel_rect.x(), sel_rect.bottom() - handle_size, handle_size, handle_size, handle_color)
                painter.fillRect(sel_rect.right() - handle_size, sel_rect.bottom() - handle_size, handle_size, handle_size, handle_color)

                # 显示选区尺寸信息
                info_text = f"{sel_rect.width()} × {sel_rect.height()}"
                painter.setPen(QColor(255, 255, 255))
                painter.drawText(sel_rect.x() + 8, sel_rect.y() - 10, info_text)
            else:
                # 没有选区时覆盖全屏半透明遮罩
                painter.fillRect(self.rect(), QColor(0, 0, 0, 160))
        else:
            # 没有截图时显示提示
            painter.fillRect(self.rect(), QColor(0, 0, 0, 200))
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(self.font())
            painter.drawText(self.rect(), Qt.AlignCenter, "正在获取截图...")

    def mousePressEvent(self, event):
        """鼠标按下：开始框选"""
        if event.button() == Qt.LeftButton:
            self._selecting = True
            self._start_pos = event.position().toPoint()
            self._current_pos = self._start_pos
            self.update()

    def mouseMoveEvent(self, event):
        """鼠标移动：更新选框"""
        if self._selecting:
            self._current_pos = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        """鼠标松开：确认选区"""
        if event.button() == Qt.LeftButton and self._selecting:
            self._selecting = False
            sel_rect = self._get_normalized_rect()
            # 过滤太小或无效的选区（< 20px）
            if sel_rect.width() > 20 and sel_rect.height() > 20:
                self.region_selected.emit(sel_rect)
            else:
                self.canceled.emit()
            self.close()

    def keyPressEvent(self, event):
        """按键处理：Esc 取消"""
        if event.key() == Qt.Key_Escape:
            self.canceled.emit()
            self.close()
        super().keyPressEvent(event)

    def _get_normalized_rect(self):
        """获取标准化后的矩形（处理从右下到左上的拖拽）"""
        x1 = min(self._start_pos.x(), self._current_pos.x())
        y1 = min(self._start_pos.y(), self._current_pos.y())
        x2 = max(self._start_pos.x(), self._current_pos.x())
        y2 = max(self._start_pos.y(), self._current_pos.y())

        # 限制在屏幕范围内
        geo = self.geometry()
        x1 = max(geo.x(), min(x1, geo.right()))
        y1 = max(geo.y(), min(y1, geo.bottom()))
        x2 = max(geo.x(), min(x2, geo.right()))
        y2 = max(geo.y(), min(y2, geo.bottom()))

        return QRect(x1, y1, x2 - x1, y2 - y1)
