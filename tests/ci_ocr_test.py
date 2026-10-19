"""CI 用：生成一张带文字的图片，检查 Windows OCR 能否识别出来。"""

import os
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ocr  # noqa: E402

img = Image.new("RGB", (520, 90), "white")
font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 40)
ImageDraw.Draw(img).text((15, 20), "Hello World 2026", fill="black", font=font)
text = ocr.recognize(img)
print("OCR result:", repr(text))
assert "Hello" in text and "World" in text, text

assert ocr._tidy(["你 好 世 界", "这是 测试"]) == "你好世界这是测试"
assert ocr._tidy(["hello", "world"]) == "hello world"
print("OK")
