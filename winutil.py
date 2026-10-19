"""Windows 相关的小工具：开机自启、只允许运行一个实例、复制选中文字。"""

import ctypes
import os
import sys
import threading
import time

APP_NAME = "EasyTranslator"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
MINIMIZED_ARG = "--minimized"


# ---------------- 开机自启 ----------------
def _launch_command():
    if getattr(sys, "frozen", False):  # 打包后的 exe
        return f'"{sys.executable}" {MINIMIZED_ARG}'
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    script = os.path.abspath(sys.argv[0])
    return f'"{pythonw}" "{script}" {MINIMIZED_ARG}'


def is_autostart():
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except OSError:
        return False


def set_autostart(enabled):
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _launch_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass


# ---------------- 单实例 ----------------
_handles = []
_SHOW_EVENT = APP_NAME + "_ShowWindow"


def ensure_single_instance():
    """已经有一个在运行时：通知它显示窗口，返回 False；否则返回 True。"""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    mutex = kernel32.CreateMutexW(None, False, APP_NAME + "_SingleInstance")
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        event = kernel32.OpenEventW(0x0002, False, _SHOW_EVENT)  # EVENT_MODIFY_STATE
        if event:
            kernel32.SetEvent(event)
            kernel32.CloseHandle(event)
        return False
    _handles.append(mutex)
    return True


def listen_show_requests(callback):
    """另一个实例启动时会调用 callback（在后台线程里）。"""
    kernel32 = ctypes.windll.kernel32
    event = kernel32.CreateEventW(None, False, False, _SHOW_EVENT)
    _handles.append(event)

    def run():
        while kernel32.WaitForSingleObject(event, 0xFFFFFFFF) == 0:
            callback()

    threading.Thread(target=run, daemon=True).start()


# ---------------- 复制选中文字 ----------------
_VK_MODIFIERS = (0x10, 0x11, 0x12, 0x5B, 0x5C)  # Shift Ctrl Alt LWin RWin
_KEYUP = 0x0002


def copy_selection():
    """模拟 Ctrl+C 复制当前选中的文字。剪贴板有变化返回 True。"""
    user32 = ctypes.windll.user32
    # 等用户松开快捷键里的修饰键，否则发出去的会变成 Ctrl+Alt+C 之类
    deadline = time.time() + 1.0
    while time.time() < deadline and any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in _VK_MODIFIERS):
        time.sleep(0.02)
    for vk in _VK_MODIFIERS:  # 仍未松开的强制抬起
        if user32.GetAsyncKeyState(vk) & 0x8000:
            user32.keybd_event(vk, 0, _KEYUP, 0)

    before = user32.GetClipboardSequenceNumber()
    user32.keybd_event(0x11, 0, 0, 0)  # Ctrl
    user32.keybd_event(0x43, 0, 0, 0)  # C
    user32.keybd_event(0x43, 0, _KEYUP, 0)
    user32.keybd_event(0x11, 0, _KEYUP, 0)
    deadline = time.time() + 0.8
    while time.time() < deadline:
        if user32.GetClipboardSequenceNumber() != before:
            time.sleep(0.05)
            return True
        time.sleep(0.02)
    return False
