"""Easy Translator - 一个只有两个文本框的极简翻译工具。"""

import ctypes
import json
import os
import re
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import engines
import hotkey
import ocr
import winutil

AUTO = "自动（中⇄英）"
# 显示名称 -> 语言代码
LANGUAGES = {
    AUTO: "auto",
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
SHORT_NAMES = {"en": "英语", "zh-CN": "中文"}

CONFIG_PATH = os.path.join(
    os.environ.get("APPDATA") or os.path.expanduser("~"), "easy_translator.json"
)
DEBOUNCE_MS = 700
# 默认快捷键：截图 Ctrl+Alt+Q，划词 Ctrl+Alt+W
CTRL_ALT = hotkey.MOD_CONTROL | hotkey.MOD_ALT
DEFAULT_HOTKEYS = {
    "hotkey": {"mods": CTRL_ALT, "vk": 0x51, "label": "Ctrl+Alt+Q"},
    "select_hotkey": {"mods": CTRL_ALT, "vk": 0x57, "label": "Ctrl+Alt+W"},
}
HOTKEY_NAMES = {"hotkey": "截图翻译", "select_hotkey": "划词翻译"}


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


class HotkeyBox(tk.Label):
    """点一下后直接按组合键来录制快捷键。"""

    def __init__(self, master, value, on_error):
        super().__init__(master, text=value["label"], font=("Microsoft YaHei UI", 12), width=16,
                         relief="groove", bg="white", pady=4, takefocus=True,
                         highlightthickness=2, highlightcolor="#2563eb")
        self.value = dict(value)
        self._held = set()
        self._on_error = on_error
        self.bind("<Button-1>", lambda e: self.focus_set())
        self.bind("<KeyPress>", self._down)
        self.bind("<KeyRelease>", lambda e: (self._held.discard(e.keysym), "break")[1])
        self.bind("<FocusOut>", lambda e: self._held.clear())

    def set(self, value):
        self.value = dict(value)
        self.configure(text=value["label"])

    def _down(self, e):
        if e.keysym in hotkey.MODIFIER_KEYS:
            self._held.add(e.keysym)
            return "break"
        if e.keysym == "Tab":
            return None
        mods = 0
        for k in self._held:
            mods |= hotkey.MODIFIER_KEYS[k][0]
        name = e.keysym.upper() if len(e.keysym) == 1 else e.keysym
        if not mods and not re.fullmatch(r"F\d{1,2}", e.keysym):
            self._on_error("需要包含 Ctrl / Alt / Shift / Win 中的至少一个")
            return "break"
        self.set({"mods": mods, "vk": e.keycode, "label": hotkey.format_hotkey(mods, name)})
        self._on_error("")
        return "break"


class App:
    def __init__(self, root, start_hidden=False):
        self.root = root
        self.cfg = load_config()
        self.cfg.setdefault("tray", True)
        self.pending = None
        self.request_id = 0
        self.last_request = None
        self.capturing = False
        self.hotkeys = hotkey.HotkeyManager()
        self.tray = None
        self.tray_tip_shown = False
        self.direction = ""

        root.title("Easy Translator")
        root.geometry(self.cfg.get("geometry", "560x480"))
        root.minsize(400, 320)

        font = ("Microsoft YaHei UI", 11)
        pad = {"padx": 10, "pady": 6}

        top = ttk.Frame(root)
        top.pack(fill="x", **pad)
        ttk.Label(top, text="翻译成：").pack(side="left")
        self.lang = tk.StringVar(value=self.cfg.get("target", AUTO))
        if self.lang.get() not in LANGUAGES:
            self.lang.set(AUTO)
        combo = ttk.Combobox(
            top, textvariable=self.lang, values=list(LANGUAGES), state="readonly", width=18
        )
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", lambda e: self.translate_now(force=True))
        self.topmost = tk.BooleanVar(value=self.cfg.get("topmost", False))
        ttk.Checkbutton(top, text="📌 置顶", variable=self.topmost,
                        command=self.apply_topmost).pack(side="right")
        self.status = ttk.Label(top, text="", foreground="gray")
        self.status.pack(side="right", padx=8)

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
        ttk.Button(bottom, text="设置", command=self.open_settings).pack(side="left", padx=(8, 0))
        ttk.Button(bottom, text="复制译文", command=self.copy).pack(side="right")

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.src.focus_set()
        self.apply_topmost()
        self.apply_hotkeys(show_error=False)
        self.set_tray(self.cfg["tray"])
        if start_hidden:
            if self.tray:
                root.withdraw()
            else:
                root.iconify()

    # ---- 翻译 ----
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
        choice = LANGUAGES[self.lang.get()]
        if not force and (text, choice) == self.last_request:
            return
        self.last_request = (text, choice)
        self.request_id += 1
        if not text:
            self.set_output("")
            self.status.configure(text="")
            return
        rid = self.request_id
        if choice == "auto":
            target = engines.auto_target(text)
            self.direction = "→ " + SHORT_NAMES[target]
        else:
            target, self.direction = choice, ""
        self.status.configure(text=f"翻译中… {self.direction}")
        threading.Thread(target=self.worker, args=(rid, text, target), daemon=True).start()

    def worker(self, rid, text, target):
        def progress(done, total):
            self.root.after(0, self.show_progress, rid, done, total)

        try:
            result, status = engines.translate(text, target, progress), self.direction
        except Exception as e:  # noqa: BLE001
            result, status = str(e), "出错"
        self.root.after(0, self.show_result, rid, result, status)

    def show_progress(self, rid, done, total):
        if rid == self.request_id:
            self.status.configure(text=f"翻译中 {done}/{total}… {self.direction}")

    def show_result(self, rid, result, status):
        if rid != self.request_id:  # 已有更新的请求，丢弃旧结果
            return
        self.set_output(result)
        self.status.configure(text=status)

    def set_input_and_translate(self, text):
        self.src.delete("1.0", "end")
        self.src.insert("1.0", text)
        self.translate_now(force=True)

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
            lang = ocr.OCR_LANGUAGES.get(self.cfg.get("ocr_lang"), "auto")
            threading.Thread(target=self.ocr_worker, args=(crop, lang), daemon=True).start()

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
        self.show_window()

    def ocr_worker(self, image, lang):
        try:
            text, error = ocr.recognize(image, lang), None
        except Exception as e:  # noqa: BLE001
            text, error = "", str(e)
        self.root.after(0, self.show_ocr_result, text, error)

    def show_ocr_result(self, text, error):
        if error:
            self.status.configure(text="出错")
            messagebox.showerror("文字识别失败", error, parent=self.root)
            return
        if not text:
            self.status.configure(text="没有识别到文字")
            return
        self.set_input_and_translate(text)

    # ---- 划词翻译 ----
    def start_selection(self):
        try:
            old = self.root.clipboard_get()
        except tk.TclError:
            old = None

        def work():
            copied = winutil.copy_selection()
            self.root.after(0, self.finish_selection, copied, old)

        threading.Thread(target=work, daemon=True).start()

    def finish_selection(self, copied, old):
        text = ""
        if copied:
            try:
                text = self.root.clipboard_get().strip()
            except tk.TclError:
                pass
            if old is not None:  # 把剪贴板里原来的文字放回去
                self.root.clipboard_clear()
                self.root.clipboard_append(old)
        self.show_window()
        if text:
            self.set_input_and_translate(text)
        else:
            self.status.configure(text="没有获取到选中的文字")

    # ---- 窗口 / 托盘 ----
    def show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def apply_topmost(self):
        self.root.attributes("-topmost", self.topmost.get())
        self.cfg["topmost"] = self.topmost.get()

    def set_tray(self, enabled):
        if enabled and not self.tray:
            import tray

            self.tray = tray.Tray(
                on_show=lambda: self.root.after(0, self.show_window),
                on_capture=lambda: self.root.after(0, self.start_capture),
                on_quit=lambda: self.root.after(0, self.quit),
            )
            self.tray.start()
        elif not enabled and self.tray:
            self.tray.stop()
            self.tray = None

    def on_close(self):
        if self.tray:
            self.root.withdraw()
            if not self.tray_tip_shown:
                self.tray_tip_shown = True
                self.tray.notify("已缩小到右下角托盘，快捷键仍然可用。右键托盘图标可以退出。")
        else:
            self.quit()

    def quit(self):
        self.hotkeys.stop()
        if self.tray:
            self.tray.stop()
        self.cfg.update(target=self.lang.get(), geometry=self.root.geometry())
        save_config(self.cfg)
        self.root.destroy()

    # ---- 全局快捷键 ----
    def hotkey_value(self, key):
        return self.cfg.get(key, DEFAULT_HOTKEYS[key])

    def apply_hotkeys(self, show_error=True):
        actions = {"hotkey": self.start_capture, "select_hotkey": self.start_selection}
        bindings = {}
        for key, action in actions.items():
            hk = self.hotkey_value(key)
            bindings[key] = (hk["mods"], hk["vk"], lambda a=action: self.root.after(0, a))
        results = self.hotkeys.set_all(bindings)
        ok_capture = results.get("hotkey")
        label = self.hotkey_value("hotkey")["label"] if ok_capture else "快捷键未生效"
        self.capture_btn.configure(text=f"截图翻译 ({label})")
        failed = [f"{HOTKEY_NAMES[k]}：{self.hotkey_value(k)['label']}"
                  for k, ok in results.items() if not ok]
        if failed and show_error:
            messagebox.showwarning(
                "快捷键不可用",
                "下面的快捷键可能被其他程序占用了，请换一个组合：\n" + "\n".join(failed),
                parent=self.root,
            )
        return not failed

    # ---- 设置 ----
    def open_settings(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("设置")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        body = ttk.Frame(dlg, padding=16)
        body.pack(fill="both")

        tip = ttk.Label(body, text="", foreground="#c0392b")
        boxes = {}
        row = 0
        ttk.Label(body, text="快捷键（点一下方框，再直接按下新的组合键）",
                  foreground="gray").grid(row=row, column=0, columnspan=2, sticky="w")
        for key in DEFAULT_HOTKEYS:
            row += 1
            ttk.Label(body, text=HOTKEY_NAMES[key] + "：").grid(row=row, column=0, sticky="w", pady=4)
            boxes[key] = HotkeyBox(body, self.hotkey_value(key), lambda m: tip.configure(text=m))
            boxes[key].grid(row=row, column=1, sticky="w", pady=4)
        row += 1
        tip.grid(row=row, column=0, columnspan=2, sticky="w")

        row += 1
        ttk.Label(body, text="截图识别语言：").grid(row=row, column=0, sticky="w", pady=(10, 4))
        ocr_lang = tk.StringVar(value=self.cfg.get("ocr_lang", "自动（中文/英文）"))
        if ocr_lang.get() not in ocr.OCR_LANGUAGES:
            ocr_lang.set("自动（中文/英文）")
        ttk.Combobox(body, textvariable=ocr_lang, values=list(ocr.OCR_LANGUAGES),
                     state="readonly", width=18).grid(row=row, column=1, sticky="w", pady=(10, 4))

        row += 1
        tray_var = tk.BooleanVar(value=self.cfg["tray"])
        ttk.Checkbutton(body, text="关闭窗口时缩小到托盘（不退出）", variable=tray_var).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(10, 2))
        row += 1
        try:
            autostart_now = winutil.is_autostart()
        except Exception:  # noqa: BLE001
            autostart_now = False
        autostart_var = tk.BooleanVar(value=autostart_now)
        ttk.Checkbutton(body, text="开机自动启动（启动后缩小在托盘）", variable=autostart_var).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=2)

        def reset_hotkeys():
            for key, box in boxes.items():
                box.set(DEFAULT_HOTKEYS[key])

        def save():
            new = {key: box.value for key, box in boxes.items()}
            a, b = new["hotkey"], new["select_hotkey"]
            if (a["mods"], a["vk"]) == (b["mods"], b["vk"]):
                tip.configure(text="两个快捷键不能一样")
                return
            old = {key: self.hotkey_value(key) for key in DEFAULT_HOTKEYS}
            self.cfg.update(new)
            if not self.apply_hotkeys():
                self.cfg.update(old)  # 新的不可用，恢复原来的
                self.apply_hotkeys(show_error=False)
                return
            self.cfg["ocr_lang"] = ocr_lang.get()
            self.cfg["tray"] = tray_var.get()
            self.set_tray(tray_var.get())
            if autostart_var.get() != autostart_now:
                try:
                    winutil.set_autostart(autostart_var.get())
                except OSError as e:
                    messagebox.showerror("开机自启设置失败", str(e), parent=dlg)
            save_config(self.cfg)
            dlg.destroy()

        btns = ttk.Frame(body)
        btns.grid(row=row + 1, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        ttk.Button(btns, text="恢复默认快捷键", command=reset_hotkeys,
                   takefocus=False).pack(side="left")
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


def main():
    if not winutil.ensure_single_instance():
        return  # 已经在运行了，那个窗口会自己弹出来
    try:  # 高分屏下字体清晰，且截图坐标与屏幕像素一致
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:  # noqa: BLE001
        pass
    root = tk.Tk()
    try:
        from PIL import ImageTk

        import tray

        root._icon = ImageTk.PhotoImage(tray.make_icon(64))
        root.iconphoto(True, root._icon)
    except Exception:  # noqa: BLE001
        pass
    app = App(root, start_hidden=winutil.MINIMIZED_ARG in sys.argv)
    winutil.listen_show_requests(lambda: root.after(0, app.show_window))
    root.mainloop()


if __name__ == "__main__":
    main()
