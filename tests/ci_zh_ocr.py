"""CI 信息性测试：比较中文小字在“放大前/放大后”的识别准确度。"""

import difflib
import os
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ocr  # noqa: E402

TEXT = ["截图翻译和可设置的全局快捷键都加好了，新的程序已经打包成功。",
        "在页面底部下载解压后双击运行，替换旧版即可。识别语言可以在设置里选择。"]
font = None
for name in ("msyh.ttc", "simsun.ttc", "simhei.ttf", "Deng.ttf"):
    try:
        font = ImageFont.truetype(os.path.join(r"C:\Windows\Fonts", name), 13)
        print("font:", name)
        break
    except OSError:
        pass
if font is None:
    sys.exit("no Chinese font on this machine, skipped")

img = Image.new("RGB", (560, 44), "white")
d = ImageDraw.Draw(img)
for i, line in enumerate(TEXT):
    d.text((4, 4 + i * 19), line, fill="black", font=font)
expected = "".join(TEXT)

original_prepare = ocr.prepare
for label, prep in (("raw", lambda im: im.convert("RGB")), ("enlarged", original_prepare)):
    ocr.prepare = prep
    out = ocr.recognize(img, "zh-Hans,zh-CN")
    score = difflib.SequenceMatcher(None, expected, out).ratio()
    print(f"{label:9s} accuracy={score:.2%} -> {out}")
