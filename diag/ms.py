import json, urllib.request, urllib.error, urllib.parse
def req(url, data=None, headers=None):
    r = urllib.request.Request(url, data=data, headers={"User-Agent": "Mozilla/5.0", **(headers or {})})
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return -1, repr(e)
text = "Good morning, how are you?\nSecond line here."
form = {"Content-Type": "application/x-www-form-urlencoded"}
for name, url, body in [
    ("clients5 dict-chrome-ex GET", "https://clients5.google.com/translate_a/t?" + urllib.parse.urlencode({"client": "dict-chrome-ex", "sl": "auto", "tl": "zh-CN", "q": text}), None),
    ("clients5 dict-chrome-ex POST", "https://clients5.google.com/translate_a/t?client=dict-chrome-ex&sl=auto&tl=zh-CN", urllib.parse.urlencode({"q": text}).encode()),
    ("translate.google.com/translate_a/t gtx", "https://translate.google.com/translate_a/t?client=gtx&sl=auto&tl=zh-CN", urllib.parse.urlencode({"q": text}).encode()),
    ("translate.googleapis.com single gtx", "https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=zh-CN&dt=t", urllib.parse.urlencode({"q": text}).encode()),
    ("clients5 single gtx", "https://clients5.google.com/translate_a/single?client=gtx&sl=auto&tl=zh-CN&dt=t", urllib.parse.urlencode({"q": text}).encode()),
]:
    s, b = req(url, body, form if body else None)
    print(f"{name}: {s} {b[:200]!r}")
