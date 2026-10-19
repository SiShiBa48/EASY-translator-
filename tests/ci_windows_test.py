"""CI（Windows）测试：OCR、联网翻译长文本、快捷键注册。"""

import os
import sys
import time

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import engines  # noqa: E402
import hotkey  # noqa: E402
import ocr  # noqa: E402

# ---- OCR：英文 ----
img = Image.new("RGB", (520, 90), "white")
font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 40)
ImageDraw.Draw(img).text((15, 20), "Hello World 2026", fill="black", font=font)
for lang in ("auto", "en"):
    text = ocr.recognize(img, lang)
    print(f"OCR [{lang}]:", repr(text))
    assert "Hello" in text and "World" in text, text

# 小字号多行英文（放大处理后应能识别）
small = Image.new("RGB", (420, 60), "white")
f12 = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 12)
d = ImageDraw.Draw(small)
d.text((4, 4), "Small text should still be recognized", fill="black", font=f12)
d.text((4, 24), "after the image is enlarged first.", fill="black", font=f12)
text = ocr.recognize(small, "auto")
print("OCR small:", repr(text))
assert "recognized" in text and "enlarged" in text, text

# 没安装的识别语言要给出友好提示
try:
    ocr.recognize(img, "ko")
    print("ko OCR installed on this machine")
except RuntimeError as e:
    print("ko missing message OK:", str(e).splitlines()[0])
    assert "没有安装" in str(e)

assert ocr._tidy(["你 好 世 界", "这是 测试"]) == "你好世界这是测试"
assert ocr._tidy(["hello", "world"]) == "hello world"

# ---- 快捷键 ----
m = hotkey.HotkeyManager()
res = m.set_all({"a": (hotkey.MOD_CONTROL | hotkey.MOD_ALT, 0x51, lambda: None),
                 "b": (hotkey.MOD_CONTROL | hotkey.MOD_ALT, 0x57, lambda: None)})
print("hotkeys:", res)
assert all(res.values())
m.stop()

# ---- 联网翻译（每个引擎单独试，再整体试长文本）----
long_text = ("Machine translation has improved a lot in recent years. "
             "However, long documents still need to be split into smaller pieces. ") * 60
long_text += "\n\nThis is the final paragraph of the test document."
print("long text length:", len(long_text))
for engine in engines.ENGINES:
    t = time.time()
    try:
        out = engine("Good morning, how are you today?", "zh-CN")
        print(f"engine {engine.__name__}: OK {time.time() - t:.1f}s ->", out)
    except Exception as e:  # noqa: BLE001
        print(f"engine {engine.__name__}: FAILED -> {e!r}")

progress = []
t = time.time()
out = engines.translate(long_text, "zh-CN", lambda d, n: progress.append((d, n)))
print(f"long translate: {time.time() - t:.1f}s, chunks={progress[-1] if progress else 1},"
      f" preferred={engines._preferred['engine'].__name__}, out_len={len(out)}")
print("head:", out[:80])
print("tail:", out[-60:])
assert len(out) > 500 and "\n\n" in out
print("ALL OK")
