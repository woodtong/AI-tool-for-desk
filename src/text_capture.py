"""
文字选取模块 - 选中文本复制
使用 Win32 原生 API 实现高可靠性文本捕获
- OpenClipboard / GetClipboardSequenceNumber 检测变化
- SendInput 扫描码模式 + keybd_event 双重模拟
- 自动重试机制
"""
import time
import logging
import ctypes
from ctypes import wintypes
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

logger = logging.getLogger(__name__)

# 常量
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

VK_CONTROL = 0x11
VK_C = 0x43
VK_INSERT = 0x2D

# Ctrl 的扫描码
SCAN_CTRL = 0x1D
SCAN_C = 0x2E
SCAN_INSERT = 0x52


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk",       wintypes.WORD),
        ("wScan",     wintypes.WORD),
        ("dwFlags",   ctypes.c_ulong),
        ("time",      ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("u",    _INPUT_UNION),
    ]


def _send_key_si(vk_code, scan_code, press=True):
    """使用 SendInput 发送按键（含扫描码，可绕过部分 UIPI 限制）"""
    flags = 0 if press else KEYEVENTF_KEYUP
    inp = INPUT(
        type=INPUT_KEYBOARD,
        u=_INPUT_UNION(
            ki=KEYBDINPUT(
                wVk=vk_code,
                wScan=scan_code,
                dwFlags=flags,
                time=0,
                dwExtraInfo=None,
            )
        ),
    )
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def _send_key_ke(vk_code, press=True):
    """使用 keybd_event 发送按键（旧 API，不同权限模型）"""
    flags = 0 if press else 2  # KEYEVENTF_KEYUP
    ctypes.windll.user32.keybd_event(vk_code, 0, flags, 0)


def _ctrl_c_sendinput():
    """SendInput 方式发送 Ctrl+C"""
    _send_key_si(VK_CONTROL, SCAN_CTRL, True)
    time.sleep(0.05)
    _send_key_si(VK_C, SCAN_C, True)
    time.sleep(0.05)
    _send_key_si(VK_C, SCAN_C, False)
    time.sleep(0.05)
    _send_key_si(VK_CONTROL, SCAN_CTRL, False)


def _ctrl_c_keyevent():
    """keybd_event 方式发送 Ctrl+C"""
    _send_key_ke(VK_CONTROL, True)
    time.sleep(0.05)
    _send_key_ke(VK_C, True)
    time.sleep(0.05)
    _send_key_ke(VK_C, False)
    time.sleep(0.05)
    _send_key_ke(VK_CONTROL, False)


def _ctrl_insert_sendinput():
    """SendInput 方式发送 Ctrl+Insert（部分应用支持）"""
    _send_key_si(VK_CONTROL, SCAN_CTRL, True)
    time.sleep(0.03)
    _send_key_si(VK_INSERT, SCAN_INSERT, True)
    time.sleep(0.03)
    _send_key_si(VK_INSERT, SCAN_INSERT, False)
    time.sleep(0.03)
    _send_key_si(VK_CONTROL, SCAN_CTRL, False)


def _send_wm_copy():
    """向当前前台窗口发送 WM_COPY 消息 (0x0301)"""
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    if hwnd:
        ctypes.windll.user32.SendMessageW(hwnd, 0x0301, 0, 0)
        time.sleep(0.05)


def _clear_clipboard_win32():
    """使用 Win32 API 清空剪贴板（比 Qt 方式更可靠）"""
    user32 = ctypes.windll.user32
    if user32.OpenClipboard(None):
        user32.EmptyClipboard()
        user32.CloseClipboard()


def _get_clipboard_sequence():
    """获取剪贴板序列号，用于检测剪贴板是否变化"""
    try:
        return ctypes.windll.user32.GetClipboardSequenceNumber()
    except Exception:
        return 0


def _set_clipboard_func_types():
    """设置 Win32 剪贴板 API 的 ctypes 参数/返回类型，防止 64 位指针截断"""
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    # OpenClipboard(hwnd) -> BOOL
    user32.OpenClipboard.argtypes = [wintypes.HANDLE]
    user32.OpenClipboard.restype = wintypes.BOOL
    # CloseClipboard() -> BOOL
    user32.CloseClipboard.restype = wintypes.BOOL
    # EmptyClipboard() -> BOOL
    user32.EmptyClipboard.restype = wintypes.BOOL
    # GetClipboardData(uFormat) -> HANDLE (64-bit)
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    # GlobalLock(hMem) -> LPVOID (64-bit pointer)
    kernel32.GlobalLock.argtypes = [wintypes.HANDLE]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    # GlobalUnlock(hMem) -> BOOL
    kernel32.GlobalUnlock.argtypes = [wintypes.HANDLE]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    # GlobalSize(hMem) -> SIZE_T
    kernel32.GlobalSize.argtypes = [wintypes.HANDLE]
    kernel32.GlobalSize.restype = ctypes.c_size_t


# 模块加载时初始化函数类型声明
_set_clipboard_func_types()


def _read_clipboard_win32():
    """
    使用 Win32 API 读取剪贴板文本
    已设置正确的 64 位指针返回类型，防止句柄截断
    """
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    if not user32.OpenClipboard(None):
        return ""

    text = ""
    try:
        handle = user32.GetClipboardData(13)  # CF_UNICODETEXT
        if not handle:
            return ""

        size = kernel32.GlobalSize(handle)
        if not size or size > 1024 * 1024:  # 保护：最大 1MB
            return ""

        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return ""

        try:
            # 仅读取有效的字符数，防止越界
            char_count = size // 2  # UTF-16 每字符 2 字节
            text = ctypes.wstring_at(ptr, char_count)
        finally:
            kernel32.GlobalUnlock(handle)
    except Exception:
        text = ""
    finally:
        user32.CloseClipboard()

    return text.strip()


def _try_copy():
    """
    尝试执行复制操作，使用多种方法提高成功率
    顺序尝试各方法，一旦检测到剪贴板有内容即返回

    返回:
        bool - 是否成功复制到内容
    """
    # 保存操作前的剪贴板内容，用于判断是否变化
    _clear_clipboard_win32()

    for attempt in [
        ("WM_COPY", _send_wm_copy, 0.03),
        ("SendInput Ctrl+C", _ctrl_c_sendinput, 0.03),
        ("keybd_event Ctrl+C", _ctrl_c_keyevent, 0.03),
        ("Ctrl+Insert", _ctrl_insert_sendinput, 0.03),
    ]:
        name, func, wait = attempt
        _clear_clipboard_win32()
        func()
        time.sleep(wait)
        text = _read_clipboard_win32()
        if text:
            logger.debug("文字复制成功: 方法=%s", name)
            return True
        logger.debug("文字复制方法 %s 未生效，尝试下一方法", name)

    return False


def capture_selected_text(callback, delay_ms=400):
    """
    获取当前选中的文本

    1. 顺序尝试多种复制方式，检测到剪贴板有内容即停止
    2. 延迟后读取剪贴板文本
    3. 若未检测到变化，重试一次

    参数:
        callback: function(str) - 获取文本后的回调
        delay_ms: int - 复制后等待剪贴板同步的延迟（毫秒）
    """
    success = _try_copy()

    def _read_and_check(retry=True):
        text = "" if not success else _read_clipboard_win32()
        if not text:
            # Qt 后备读取
            try:
                text = QApplication.clipboard().text() or ""
            except Exception:
                text = ""

        if not text and retry:
            # 首次失败，重试一次
            if not _try_copy():
                QTimer.singleShot(delay_ms + 100, lambda: _read_and_check(retry=False))
                return
            text = _read_clipboard_win32() or ""
            if not text:
                try:
                    text = QApplication.clipboard().text() or ""
                except Exception:
                    text = ""

        try:
            callback(text)
        except Exception:
            pass

    QTimer.singleShot(delay_ms, _read_and_check)
