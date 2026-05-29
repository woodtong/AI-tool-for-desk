"""
截图模块 - 全屏截图、区域选取、图片编码
使用 mss 库快速截屏，QImage 处理像素转换，Pillow 编码图片
"""
import io
import base64
from PIL import Image
import mss
from PySide6.QtCore import Qt, QByteArray, QBuffer
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import QApplication


def capture_fullscreen():
    """
    捕获全屏截图（保留原始物理分辨率）

    返回:
        QPixmap: 全屏截图（原始物理像素尺寸）
    """
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        s = sct.grab(monitor)
        qimg = QImage(s.bgra, s.width, s.height, QImage.Format_ARGB32)
        return QPixmap.fromImage(qimg)


def scale_for_display(pixmap):
    """
    将物理分辨率截图缩放到屏幕逻辑像素尺寸（用于显示适配高 DPI）

    参数:
        pixmap: QPixmap - 物理分辨率截图

    返回:
        QPixmap: 缩放后的显示用截图
    """
    app = QApplication.instance()
    if app and app.primaryScreen():
        logical = app.primaryScreen().size()
        if pixmap.width() != logical.width() or pixmap.height() != logical.height():
            return pixmap.scaled(
                logical.width(), logical.height(),
                Qt.IgnoreAspectRatio, Qt.FastTransformation
            )
    return pixmap


def get_screen_dpr(pixmap):
    """
    计算屏幕 DPI 缩放比（物理像素 / 逻辑像素）

    参数:
        pixmap: QPixmap - 物理分辨率截图

    返回:
        float: 缩放比，无缩放时返回 1.0
    """
    app = QApplication.instance()
    if app and app.primaryScreen():
        logical = app.primaryScreen().size()
        if pixmap.width() != logical.width() and logical.width() > 0:
            return pixmap.width() / logical.width()
    return 1.0


def crop_from_screen(rect, device_pixel_ratio=1.0):
    """
    从全屏截图中裁剪指定区域

    参数:
        rect: QRect - 选中的区域（设备独立像素坐标）
        device_pixel_ratio: float - 屏幕 DPI 缩放比

    返回:
        PIL.Image: 裁剪后的图片（RGB）
    """
    # 将 Qt 逻辑坐标转换为实际物理像素坐标
    x = int(rect.x() * device_pixel_ratio)
    y = int(rect.y() * device_pixel_ratio)
    w = int(rect.width() * device_pixel_ratio)
    h = int(rect.height() * device_pixel_ratio)

    with mss.mss() as sct:
        monitor = {"left": x, "top": y, "width": w, "height": h}
        s = sct.grab(monitor)

    # mss BGRA -> QImage(ARGB32) -> RGBA8888 bytes -> PIL Image
    qimg = QImage(s.bgra, s.width, s.height, QImage.Format_ARGB32)
    rgba = qimg.convertToFormat(QImage.Format_RGBA8888)
    ptr = rgba.constBits()

    # PySide6 不同版本返回 voidptr 或 memoryview
    if hasattr(ptr, 'setsize'):
        ptr.setsize(rgba.sizeInBytes())
    data = bytes(ptr)

    return Image.frombytes("RGBA", (rgba.width(), rgba.height()), data).convert("RGB")


def image_to_base64(image, format="PNG"):
    """
    将 PIL Image 编码为 base64 字符串
    """
    buffered = io.BytesIO()
    if format == "JPEG":
        image = image.convert("RGB")
        image.save(buffered, format="JPEG", quality=85)
    else:
        image.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")


def pixmap_to_base64(pixmap):
    """
    将 QPixmap 编码为 base64 PNG 字符串
    """
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QBuffer.WriteOnly)
    pixmap.save(buf, "PNG")
    buf.close()
    return base64.b64encode(data.data()).decode("utf-8")


def capture_region(rect, device_pixel_ratio=1.0):
    """
    便捷方法：截取指定区域并返回 base64 编码
    """
    img = crop_from_screen(rect, device_pixel_ratio)
    b64 = image_to_base64(img)
    return img, b64
