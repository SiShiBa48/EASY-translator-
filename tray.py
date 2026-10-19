"""系统托盘图标。"""

import threading

import pystray
from PIL import Image, ImageDraw, ImageFont


def make_icon(size=64):
    """蓝底白字“译”的图标；找不到中文字体时用 T。"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=size // 5, fill=(37, 99, 235))
    for font_file, char in (("msyhbd.ttc", "译"), ("msyh.ttc", "译"), ("arialbd.ttf", "T")):
        try:
            font = ImageFont.truetype(font_file, int(size * 0.62))
            break
        except OSError:
            continue
    else:
        font, char = ImageFont.load_default(), "T"
    draw.text((size / 2, size / 2), char, font=font, fill="white", anchor="mm")
    return img


class Tray:
    def __init__(self, on_show, on_capture, on_quit):
        menu = pystray.Menu(
            pystray.MenuItem("显示窗口", lambda icon, item: on_show(), default=True),
            pystray.MenuItem("截图翻译", lambda icon, item: on_capture()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", lambda icon, item: on_quit()),
        )
        self.icon = pystray.Icon("EasyTranslator", make_icon(), "Easy Translator", menu)

    def start(self):
        threading.Thread(target=self.icon.run, daemon=True).start()

    def notify(self, message):
        try:
            self.icon.notify(message, "Easy Translator")
        except Exception:  # noqa: BLE001
            pass

    def stop(self):
        try:
            self.icon.stop()
        except Exception:  # noqa: BLE001
            pass
