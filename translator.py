"""Easy Translator - 一个只有两个文本框的极简翻译工具。"""

import json
import os
import re
import threading
import tkinter as tk
import urllib.parse
import urllib.request
from tkinter import ttk

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
        combo.bind("<<ComboboxSelected>>", lambda e: self.translate_now())
        self.status = ttk.Label(top, text="", foreground="gray")
        self.status.pack(side="right")

        self.src = tk.Text(root, height=8, wrap="word", font=font, undo=True)
        self.src.pack(fill="both", expand=True, **pad)
        self.src.bind("<<Modified>>", self.on_modified)
        self.src.bind("<Control-Return>", lambda e: (self.translate_now(), "break")[1])

        self.dst = tk.Text(root, height=8, wrap="word", font=font, bg="#f5f5f5")
        self.dst.pack(fill="both", expand=True, **pad)
        self.dst.configure(state="disabled")

        bottom = ttk.Frame(root)
        bottom.pack(fill="x", **pad)
        ttk.Button(bottom, text="清空", command=self.clear).pack(side="left")
        ttk.Button(bottom, text="复制译文", command=self.copy).pack(side="right")

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.src.focus_set()

    # ---- 事件 ----
    def on_modified(self, _event):
        if not self.src.edit_modified():
            return
        self.src.edit_modified(False)
        if self.pending:
            self.root.after_cancel(self.pending)
        self.pending = self.root.after(DEBOUNCE_MS, self.translate_now)

    def translate_now(self):
        self.pending = None
        text = self.src.get("1.0", "end").strip()
        self.request_id += 1
        if not text:
            self.set_output("")
            self.status.configure(text="")
            return
        rid = self.request_id
        target = LANGUAGES[self.lang.get()]
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
        self.cfg.update(target=self.lang.get(), geometry=self.root.geometry())
        save_config(self.cfg)
        self.root.destroy()


def main():
    try:  # 高分屏下字体清晰
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001
        pass
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
