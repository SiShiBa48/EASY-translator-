"""使用 Win32 RegisterHotKey 注册全局快捷键（软件在后台也能触发）。"""

import ctypes
import threading

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012
_HOTKEY_ID = 1

# Tk 修饰键名称 -> (Win32 修饰符, 显示名)
MODIFIER_KEYS = {
    "Control_L": (MOD_CONTROL, "Ctrl"), "Control_R": (MOD_CONTROL, "Ctrl"),
    "Alt_L": (MOD_ALT, "Alt"), "Alt_R": (MOD_ALT, "Alt"),
    "Shift_L": (MOD_SHIFT, "Shift"), "Shift_R": (MOD_SHIFT, "Shift"),
    "Win_L": (MOD_WIN, "Win"), "Win_R": (MOD_WIN, "Win"),
}
_MOD_ORDER = [(MOD_CONTROL, "Ctrl"), (MOD_ALT, "Alt"), (MOD_SHIFT, "Shift"), (MOD_WIN, "Win")]


def format_hotkey(mods, key_name):
    parts = [name for flag, name in _MOD_ORDER if mods & flag]
    return "+".join(parts + [key_name])


class GlobalHotkey:
    def __init__(self):
        self._thread = None
        self._thread_id = None

    def register(self, mods, vk, callback):
        """注册快捷键（会先注销旧的）。成功返回 True，被其他程序占用等情况返回 False。"""
        self.unregister()
        ready = threading.Event()
        result = {}

        def run():
            user32 = ctypes.windll.user32
            self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
            ok = user32.RegisterHotKey(None, _HOTKEY_ID, mods | MOD_NOREPEAT, vk)
            result["ok"] = bool(ok)
            ready.set()
            if not ok:
                return
            msg = ctypes.wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    callback()
            user32.UnregisterHotKey(None, _HOTKEY_ID)

        import ctypes.wintypes  # noqa: F401  仅 Windows 可用

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        ready.wait(3)
        if not result.get("ok"):
            self._thread = self._thread_id = None
            return False
        return True

    def unregister(self):
        if self._thread and self._thread_id:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            self._thread.join(2)
        self._thread = self._thread_id = None
