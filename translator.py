"""Easy Translator - 一个只有两个文本框的极简翻译工具。"""

import ctypes
import json
import os
import re
import threading
import tkinter as tk
import urllib.parse
import urllib.request
from tkinter import messagebox, ttk

import hotkey
import ocr

# 显示名称 -> 语言代码
LANGUAGES = {
    "英语 English": "en",
    "中文（简体）": "zh-CN",
    "中文（繁體）": "zh-TW",
    "日语 日本語": "ja",
    "韩语 한국어": "ko",
    "法语 Français": "fr",
    "德语 Deutsch": "de",
    "西班牙语 Español": "es",
    "俄语 Русский": "ru",
    "葡萄牙语 Português": "pt",
    "意大利语 Italiano": "it",
    "泰语 ไทย": "th",
    "越南语 Tiếng Việt": "vi",
    "阿拉伯语 العربية": "ar",
}

CONFIG_PATH = os.path.join(
    os.environ.get("APPDATA") or os.path.expanduser("~"), "easy_translator.json"
)
TIMEOUT = 8
DEBOUNCE_MS = 700
# 默认截图快捷键：Ctrl+Alt+Q
DEFAULT_HOTKEY = {"mods": hotkey.MOD_CONTROL | hotkey.MOD_ALT, "vk": 0x51, "label": "Ctrl+Alt+Q"}


def _get_json(url, data=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def translate_google(text, target):
    url = "https://translate.googleapis.com/translate_a/single?" + urllib.parse.urlencode(
        {"client": "gtx", "sl": "auto", "tl": target, "dt": "t"}
    )
    data = _get_json(url, urllib.parse.urlencode({"q": text}).encode("utf-8"))
    return "".join(part[0] for part in data[0] if part[0])


def translate_mymemory(text, target):
    # MyMemory 不支持自动识别，根据是否含汉字粗略判断源语言
    source = "zh-CN" if re.search(r"[一-鿿]", text) else "en"
    if source == target:
        return text
    url = "https://api.mymemory.translated.net/get?" + urllib.parse.urlencode(
        {"q": text, "langpair": f"{source}|{target}"}
    )
    data = _get_json(url)
    if data.get("responseStatus") != 200:
        raise RuntimeError(data.get("responseDetails", "翻译失败"))
    return data["responseData"]["translatedText"]


def translate(text, target):
    """优先使用 Google，失败（例如网络受限）时自动切换到 MyMemory。"""
    errors = []
    for engine in (translate_google, translate_mymemory):
        try:
            return engine(text, target)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{engine.__name__}: {e}")
    raise RuntimeError("翻译失败，请检查网络连接。\n" + "\n".join(errors))


def load_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False)
    except OSError:
        pass


class App:
    def __init__(self, root):
        self.root = root
        self.cfg = load_config()
        self.pending = None
        self.request_id = 0
        self.last_request = None
        self.capturing = False
        self.hotkey = hotkey.GlobalHotkey()

        root.title("Easy Translator")
        root.geometry(self.cfg.get("geometry", "560x480"))
        root.minsize(360, 320)

        font = ("Microsoft YaHei UI", 11)
        pad = {"padx": 10, "pady": 6}

        top = ttk.Frame(root)
        top.pack(fill="x", **pad)
        ttk.Label(top, text="翻译成：").pack(side="left")
        self.lang = tk.StringVar(value=self.cfg.get("target", "英语 English"))
        if self.lang.get() not in LANGUAGES:
            self.lang.set("英语 English")
        combo = ttk.Combobox(
            top, textvariable=self.lang, values=list(LANGUAGES), state="readonly", width=18
        )
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", lambda e: self.translate_now(force=True))
        self.status = ttk.Label(top, text="", foreground="gray")
        self.status.pack(side="right")

        self.src = tk.Text(root, height=8, wrap="word", font=font, undo=True)
        self.src.pack(fill="both", expand=True, **pad)
        self.src.bind("<<Modified>>", self.on_modified)
        self.src.bind("<Control-Return>", lambda e: (self.translate_now(force=True), "break")[1])

        self.dst = tk.Text(root, height=8, wrap="word", font=font, bg="#f5f5f5")
        self.dst.pack(fill="both", expand=True, **pad)
        self.dst.configure(state="disabled")

        bottom = ttk.Frame(root)
        bottom.pack(fill="x", **pad)
        ttk.Button(bottom, text="清空", command=self.clear).pack(side="left")
        self.capture_btn = ttk.Button(bottom, command=self.start_capture)
        self.capture_btn.pack(side="left", padx=(8, 0))
        ttk.Button(bottom, text="快捷键设置", command=self.open_hotkey_dialog).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(bottom, text="复制译文", command=self.copy).pack(side="right")

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.src.focus_set()
        self.apply_hotkey(self.cfg.get("hotkey", DEFAULT_HOTKEY), show_error=False)

    # ---- 事件 ----
    def on_modified(self, _event):
        if not self.src.edit_modified():
            return
        self.src.edit_modified(False)
        if self.pending:
            self.root.after_cancel(self.pending)
        self.pending = self.root.after(DEBOUNCE_MS, self.translate_now)

    def translate_now(self, force=False):
        if self.pending:
            self.root.after_cancel(self.pending)
        self.pending = None
        text = self.src.get("1.0", "end").strip()
        target = LANGUAGES[self.lang.get()]
        if not force and (text, target) == self.last_request:
            return
        self.last_request = (text, target)
        self.request_id += 1
        if not text:
            self.set_output("")
            self.status.configure(text="")
            return
        rid = self.request_id
        self.status.configure(text="翻译中…")
        threading.Thread(target=self.worker, args=(rid, text, target), daemon=True).start()

    def worker(self, rid, text, target):
        try:
            result, status = translate(text, target), ""
        except Exception as e:  # noqa: BLE001
            result, status = str(e), "出错"
        self.root.after(0, self.show_result, rid, result, status)

    def show_result(self, rid, result, status):
        if rid != self.request_id:  # 已有更新的请求，丢弃旧结果
            return
        self.set_output(result)
        self.status.configure(text=status)

    # ---- 截图翻译 ----
    def start_capture(self):
        if self.capturing:
            return
        self.capturing = True
        self.root.withdraw()  # 先隐藏自己，免得挡住要截的内容
        self.root.after(250, self.show_overlay)

    def show_overlay(self):
        from PIL import ImageGrab

        try:
            shot = ImageGrab.grab(all_screens=True)
        except Exception as e:  # noqa: BLE001
            self.finish_capture()
            messagebox.showerror("截图失败", str(e))
            return

        # 覆盖所有显示器的虚拟屏幕区域
        m = ctypes.windll.user32.GetSystemMetrics
        vx, vy, vw, vh = m(76), m(77), m(78), m(79)

        overlay = tk.Toplevel(self.root)
        overlay.overrideredirect(True)
        overlay.geometry(f"{vw}x{vh}+{vx}+{vy}")
        overlay.attributes("-topmost", True)
        overlay.attributes("-alpha", 0.3)
        canvas = tk.Canvas(overlay, bg="black", cursor="crosshair", highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        canvas.create_text(
            m(0) // 2 - vx, 40 - vy, fill="white", font=("Microsoft YaHei UI", 16),
            text="拖动鼠标框选要翻译的文字，按 Esc 或右键取消",
        )
        state = {}

        def press(e):
            state["start"] = (e.x, e.y)
            state["rect"] = canvas.create_rectangle(e.x, e.y, e.x, e.y, outline="red", width=2,
                                                    fill="white")

        def drag(e):
            if "rect" in state:
                x0, y0 = state["start"]
                canvas.coords(state["rect"], x0, y0, e.x, e.y)

        def release(e):
            if "start" not in state:
                return
            x0, y0 = state["start"]
            overlay.destroy()
            left, right = sorted((x0, e.x))
            top, bottom = sorted((y0, e.y))
            if right - left < 5 or bottom - top < 5:
                self.finish_capture()
                return
            sx, sy = shot.width / vw, shot.height / vh
            crop = shot.crop((int(left * sx), int(top * sy), int(right * sx), int(bottom * sy)))
            self.finish_capture()
            self.status.configure(text="识别中…")
            threading.Thread(target=self.ocr_worker, args=(crop,), daemon=True).start()

        def cancel(_e=None):
            overlay.destroy()
            self.finish_capture()

        canvas.bind("<ButtonPress-1>", press)
        canvas.bind("<B1-Motion>", drag)
        canvas.bind("<ButtonRelease-1>", release)
        canvas.bind("<Button-3>", cancel)
        overlay.bind("<Escape>", cancel)
        overlay.focus_force()

    def finish_capture(self):
        self.capturing = False
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def ocr_worker(self, image):
        try:
            text, error = ocr.recognize(image), None
        except Exception as e:  # noqa: BLE001
            text, error = "", str(e)
        self.root.after(0, self.show_ocr_result, text, error)

    def show_ocr_result(self, text, error):
        if error:
            self.status.configure(text="出错")
            messagebox.showerror("文字识别失败", error)
            return
        if not text:
            self.status.configure(text="没有识别到文字")
            return
        self.src.delete("1.0", "end")
        self.src.insert("1.0", text)
        self.translate_now()

    # ---- 全局快捷键 ----
    def apply_hotkey(self, hk, show_error=True):
        ok = self.hotkey.register(hk["mods"], hk["vk"], lambda: self.root.after(0, self.start_capture))
        label = hk["label"] if ok else "未设置"
        self.capture_btn.configure(text=f"截图翻译 ({label})")
        if not ok and show_error:
            messagebox.showwarning(
                "快捷键不可用", f"快捷键 {hk['label']} 可能被其他程序占用了，请换一个组合。"
            )
        return ok

    def open_hotkey_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("设置截图快捷键")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

        current = self.cfg.get("hotkey", DEFAULT_HOTKEY)
        ttk.Label(dlg, text="请直接按下新的快捷键组合（例如 Ctrl+Alt+Q）：").pack(padx=16, pady=(14, 6))
        shown = tk.StringVar(value=current["label"])
        box = tk.Label(dlg, textvariable=shown, font=("Microsoft YaHei UI", 14), width=20,
                       relief="groove", bg="white", pady=8)
        box.pack(padx=16, pady=4)
        tip = ttk.Label(dlg, text="", foreground="gray")
        tip.pack(padx=16)

        held = set()
        chosen = {}

        def key_down(e):
            if e.keysym in hotkey.MODIFIER_KEYS:
                held.add(e.keysym)
                return "break"
            mods = 0
            for k in held:
                mods |= hotkey.MODIFIER_KEYS[k][0]
            name = e.keysym.upper() if len(e.keysym) == 1 else e.keysym
            is_fkey = re.fullmatch(r"F\d{1,2}", e.keysym) is not None
            if not mods and not is_fkey:
                tip.configure(text="需要包含 Ctrl / Alt / Shift / Win 中的至少一个")
                return "break"
            label = hotkey.format_hotkey(mods, name)
            chosen.update(mods=mods, vk=e.keycode, label=label)
            shown.set(label)
            tip.configure(text="")
            return "break"

        def key_up(e):
            held.discard(e.keysym)
            return "break"

        dlg.bind("<KeyPress>", key_down)
        dlg.bind("<KeyRelease>", key_up)

        def save():
            if chosen:
                if self.apply_hotkey(chosen):
                    self.cfg["hotkey"] = dict(chosen)
                    save_config(self.cfg)
                else:  # 新的不可用，恢复旧的
                    self.apply_hotkey(current, show_error=False)
                    return
            dlg.destroy()

        def reset():
            chosen.clear()
            chosen.update(DEFAULT_HOTKEY)
            shown.set(DEFAULT_HOTKEY["label"])

        btns = ttk.Frame(dlg)
        btns.pack(fill="x", padx=16, pady=12)
        ttk.Button(btns, text="恢复默认", command=reset, takefocus=False).pack(side="left")
        ttk.Button(btns, text="取消", command=dlg.destroy, takefocus=False).pack(side="right")
        ttk.Button(btns, text="保存", command=save, takefocus=False).pack(side="right", padx=6)
        dlg.focus_force()

    # ---- 辅助 ----
    def set_output(self, text):
        self.dst.configure(state="normal")
        self.dst.delete("1.0", "end")
        self.dst.insert("1.0", text)
        self.dst.configure(state="disabled")

    def clear(self):
        self.src.delete("1.0", "end")
        self.src.focus_set()

    def copy(self):
        text = self.dst.get("1.0", "end").strip()
        if text:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.status.configure(text="已复制")

    def on_close(self):
        self.hotkey.unregister()
        self.cfg.update(target=self.lang.get(), geometry=self.root.geometry())
        save_config(self.cfg)
        self.root.destroy()


def main():
    try:  # 高分屏下字体清晰，且截图坐标与屏幕像素一致
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:  # noqa: BLE001
        pass
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
