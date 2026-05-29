"""
全局热键管理器 - 通过 Win32 RegisterHotKey API 注册系统级热键
通过 Qt 的 QAbstractNativeEventFilter 拦截 WM_HOTKEY 消息
无需管理员权限即可使用（与 Windows 原生热键机制相同）
"""
import ctypes
import logging
from ctypes import wintypes
from PySide6.QtCore import QAbstractNativeEventFilter

logger = logging.getLogger(__name__)

# Win32 修饰键常量
MOD_ALT      = 0x0001
MOD_CONTROL  = 0x0002
MOD_SHIFT    = 0x0004
MOD_WIN      = 0x0008
MOD_NOREPEAT = 0x4000  # 防止长按重复触发

# 修饰键字符串到 Win32 常量的映射
MOD_MAP = {
    "alt":   MOD_ALT,
    "ctrl":  MOD_CONTROL,
    "shift": MOD_SHIFT,
    "win":   MOD_WIN,
}

# 键名到虚拟键码的映射（常用键）
VK_MAP = {
    # 字母
    "a": 0x41, "b": 0x42, "c": 0x43, "d": 0x44,
    "e": 0x45, "f": 0x46, "g": 0x47, "h": 0x48,
    "i": 0x49, "j": 0x4A, "k": 0x4B, "l": 0x4C,
    "m": 0x4D, "n": 0x4E, "o": 0x4F, "p": 0x50,
    "q": 0x51, "r": 0x52, "s": 0x53, "t": 0x54,
    "u": 0x55, "v": 0x56, "w": 0x57, "x": 0x58,
    "y": 0x59, "z": 0x5A,
    # 数字
    "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33,
    "4": 0x34, "5": 0x35, "6": 0x36, "7": 0x37,
    "8": 0x38, "9": 0x39,
    # 功能键
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    # 特殊键
    "space": 0x20, "enter": 0x0D, "esc": 0x1B,
    "tab": 0x09, "backspace": 0x08,
}

user32 = ctypes.windll.user32


class HotkeyManager(QAbstractNativeEventFilter):
    """
    全局热键管理器
    用法:
        mgr = HotkeyManager()
        mgr.register("win+shift", "f", lambda: print("热键触发!"))
        app.installNativeEventFilter(mgr)
    """

    WM_HOTKEY = 0x0312

    def __init__(self):
        super().__init__()
        # hotkey_id -> callback 函数
        self._callbacks = {}
        # 自增 ID，每次注册 +1
        self._next_id = 1000

    def register(self, modifier_str, key_str, callback):
        """
        注册一个全局热键

        参数:
            modifier_str: 修饰键字符串，如 "win+shift", "ctrl+alt"
            key_str:      键名，如 "f", "s", "space", "f1"
            callback:     触发时执行的无参函数

        返回: hotkey_id (可用于注销)，失败返回 None
        """
        # 解析修饰键
        mod = 0
        for part in modifier_str.lower().split("+"):
            part = part.strip()
            if part in MOD_MAP:
                mod |= MOD_MAP[part]
            else:
                logger.warning("未知的修饰键 '%s'", part)
                return None

        # 解析键名
        key = key_str.lower()
        vk = VK_MAP.get(key)
        if vk is None:
            logger.warning("不支持的键 '%s'", key_str)
            return None

        # 分配 ID 并注册
        hotkey_id = self._next_id
        self._next_id += 1

        # MOD_NOREPEAT 防止按住时重复触发
        if not user32.RegisterHotKey(None, hotkey_id, mod | MOD_NOREPEAT, vk):
            err = ctypes.GetLastError()
            logger.warning("热键 [%s+%s] 注册失败 (mod=0x%X, vk=0x%X, err=%d)",
                           modifier_str, key_str, mod | MOD_NOREPEAT, vk, err)
            return None

        self._callbacks[hotkey_id] = callback
        logger.info("热键 [%s+%s] 注册成功 (ID=%d)", modifier_str, key_str, hotkey_id)
        return hotkey_id

    def unregister(self, hotkey_id):
        """注销指定热键"""
        if hotkey_id in self._callbacks:
            user32.UnregisterHotKey(None, hotkey_id)
            del self._callbacks[hotkey_id]

    def unregister_all(self):
        """注销所有已注册的热键"""
        for hid in list(self._callbacks.keys()):
            self.unregister(hid)

    def nativeEventFilter(self, event_type, message):
        """
        Qt 原生事件过滤器
        拦截 WM_HOTKEY 消息并映射到对应的回调函数

        参数:
            event_type: bytes - 在 Windows 上为 b"windows_generic_MSG"
            message: VoidPtr - 指向 MSG 结构体的指针（PySide6 中非下标类型）
        """
        if event_type in ("windows_generic_MSG", b"windows_generic_MSG"):
            # PySide6 中 message 是 VoidPtr，直接取地址
            msg_ptr = int(message)
            msg = ctypes.wintypes.MSG.from_address(msg_ptr)

            if msg.message == self.WM_HOTKEY:
                hotkey_id = msg.wParam
                if hotkey_id in self._callbacks:
                    try:
                        self._callbacks[hotkey_id]()
                        return True, 0
                    except Exception as e:
                        logger.error("热键回调异常 (ID=%d): %s", hotkey_id, e, exc_info=True)
                        return True, 0

        return False, 0
