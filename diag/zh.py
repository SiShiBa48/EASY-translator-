import difflib, os, sys
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter
sys.path.insert(0, os.getcwd())
import ocr
TEXT = ["截图翻译和可设置的全局快捷键都加好了，新的程序已经打包成功。",
        "在页面底部下载解压后双击运行，替换旧版即可。识别语言可以在设置里选择。"]
exp = "".join(TEXT)
def scaled(k, gray=False, contrast=False, sharpen=False):
    def f(im):
        im = im.convert("L" if gray else "RGB")
        if contrast: im = ImageOps.autocontrast(im)
        im = im.resize((im.width*k, im.height*k), Image.LANCZOS) if k > 1 else im
        if sharpen: im = im.filter(ImageFilter.SHARPEN)
        im = ImageOps.expand(im, border=20, fill=im.getpixel((0, 0)))
        return im.convert("RGB")
    return f
variants = {"raw": scaled(1), "x2": scaled(2), "x3": scaled(3), "x4": scaled(4),
            "x3gray": scaled(3, gray=True), "x3gray_contrast": scaled(3, True, True),
            "x3sharpen": scaled(3, sharpen=True), "x2sharpen": scaled(2, sharpen=True),
            "current": ocr.prepare}
for fontname in ("msyh.ttc", "simsun.ttc"):
    for size in (12, 13, 15, 18):
        try:
            font = ImageFont.truetype(os.path.join(r"C:\Windows\Fonts", fontname), size)
        except OSError:
            continue
        img = Image.new("RGB", (size * 40, size * 3 + 10), "white")
        d = ImageDraw.Draw(img)
        for i, line in enumerate(TEXT):
            d.text((4, 4 + i * int(size * 1.5)), line, fill="black", font=font)
        for name, prep in variants.items():
            ocr.prepare = prep
            out = ocr.recognize(img, "zh-Hans,zh-CN")
            print(f"{fontname} {size}px {name:16s} {difflib.SequenceMatcher(None, exp, out).ratio():.0%}")
