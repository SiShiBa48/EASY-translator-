"""使用 Win32 RegisterHotKey 注册全局快捷键（软件在后台也能触发）。"""

import ctypes
import threading

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012

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


class HotkeyManager:
    """在一个后台线程里注册多个全局快捷键。"""

    def __init__(self):
        self._thread = None
        self._thread_id = None

    def set_all(self, bindings):
        """bindings: {名称: (mods, vk, callback)}。会先注销旧的全部快捷键。
        返回 {名称: 是否注册成功}（失败一般是被其他程序占用）。"""
        self.stop()
        ready = threading.Event()
        results = {}

        def run():
            import ctypes.wintypes

            user32 = ctypes.windll.user32
            self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
            callbacks = {}
            for hid, (name, (mods, vk, cb)) in enumerate(bindings.items(), start=1):
                ok = bool(user32.RegisterHotKey(None, hid, mods | MOD_NOREPEAT, vk))
                results[name] = ok
                if ok:
                    callbacks[hid] = cb
            ready.set()
            msg = ctypes.wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY and msg.wParam in callbacks:
                    callbacks[msg.wParam]()
            for hid in callbacks:
                user32.UnregisterHotKey(None, hid)

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        ready.wait(3)
        return results

    def stop(self):
        if self._thread and self._thread_id:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            self._thread.join(2)
        self._thread = self._thread_id = None
