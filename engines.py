"""翻译引擎、长文本分段与自动翻译方向。

长文本处理：先按段落、再按句子、再按逗号/空格切成不超过 CHUNK_SIZE 的小段，
多段并行翻译后按原顺序拼回去，段落换行保持不变。
每一段依次尝试 Google → 微软 → MyMemory，哪个可用就记住哪个，后面优先用它。
"""

import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

TIMEOUT = 10
CHUNK_SIZE = 1500  # 每段最大字符数（Google/微软都能稳定处理）
MYMEMORY_LIMIT = 450  # MyMemory 单次上限约 500 字符
WORKERS = 3  # 同时翻译的段数，太多容易被限流

_CJK = re.compile(r"[㐀-鿿]")
_LATIN = re.compile(r"[A-Za-z]")
_KANA = re.compile(r"[぀-ヿ]")
_HANGUL = re.compile(r"[가-힯]")

# 依次尝试的切分位置：换行 → 句末 → 逗号等 → 空白
_SEPARATORS = [
    r"(?<=\n)",
    r"(?<=[。！？；…])|(?<=[.!?;])(?=\s)",
    r"(?<=[,，、:：])",
    r"(?<=\s)",
]


# ---------------- 自动方向 ----------------
def auto_target(text):
    """中文为主 → 英文；其他 → 简体中文。"""
    cjk = len(_CJK.findall(text))
    latin = len(_LATIN.findall(text))
    return "en" if cjk and cjk * 3 >= latin else "zh-CN"


# ---------------- 长文本分段 ----------------
def _split(text, limit, seps):
    if len(text) <= limit:
        return [text]
    if not seps:
        return [text[i:i + limit] for i in range(0, len(text), limit)]
    parts = [p for p in re.split(seps[0], text) if p]
    if len(parts) == 1:
        return _split(text, limit, seps[1:])
    out = []
    for p in parts:
        out.extend(_split(p, limit, seps[1:]))
    return out


def split_text(text, limit=CHUNK_SIZE):
    """切成每段不超过 limit 的若干段，''.join(结果) == text。"""
    chunks, buf = [], ""
    for piece in _split(text, limit, _SEPARATORS):
        if buf and len(buf) + len(piece) > limit:
            chunks.append(buf)
            buf = ""
        buf += piece
    if buf:
        chunks.append(buf)
    return chunks


# ---------------- 各个引擎 ----------------
def _request(url, data=None, headers=None):
    req = urllib.request.Request(
        url, data=data, headers={"User-Agent": "Mozilla/5.0", **(headers or {})}
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read().decode("utf-8")


def translate_google(text, target):
    url = "https://translate.googleapis.com/translate_a/single?" + urllib.parse.urlencode(
        {"client": "gtx", "sl": "auto", "tl": target, "dt": "t"}
    )
    body = urllib.parse.urlencode({"q": text}).encode("utf-8")
    data = json.loads(_request(url, body, {"Content-Type": "application/x-www-form-urlencoded"}))
    return "".join(part[0] for part in data[0] if part[0])


_ms_token = {"value": None, "time": 0.0}
_ms_lock = threading.Lock()
_MS_LANG = {"zh-CN": "zh-Hans", "zh-TW": "zh-Hant"}


def _microsoft_token():
    with _ms_lock:
        if not _ms_token["value"] or time.time() - _ms_token["time"] > 8 * 60:
            _ms_token["value"] = _request("https://edge.microsoft.com/translate/auth").strip()
            _ms_token["time"] = time.time()
        return _ms_token["value"]


def translate_microsoft(text, target):
    url = "https://api-edge.cognitive.microsofttranslator.com/translate?" + urllib.parse.urlencode(
        {"api-version": "3.0", "to": _MS_LANG.get(target, target)}
    )
    body = json.dumps([{"Text": text}]).encode("utf-8")
    headers = {"Authorization": "Bearer " + _microsoft_token(), "Content-Type": "application/json"}
    data = json.loads(_request(url, body, headers))
    return data[0]["translations"][0]["text"]


def _guess_source(text):
    if _KANA.search(text):
        return "ja"
    if _HANGUL.search(text):
        return "ko"
    if _CJK.search(text):
        return "zh-CN"
    return "en"


def translate_mymemory(text, target):
    source = _guess_source(text)
    if source == target:
        return text
    out = []
    for piece in split_text(text, MYMEMORY_LIMIT):
        url = "https://api.mymemory.translated.net/get?" + urllib.parse.urlencode(
            {"q": piece, "langpair": f"{source}|{target}"}
        )
        data = json.loads(_request(url))
        if data.get("responseStatus") != 200:
            raise RuntimeError(data.get("responseDetails", "翻译失败"))
        out.append(data["responseData"]["translatedText"])
    return " ".join(out)


ENGINES = [translate_google, translate_microsoft, translate_mymemory]
_preferred = {"engine": ENGINES[0]}


def _try_engine(engine, text, target):
    try:
        return engine(text, target)
    except urllib.error.HTTPError as e:
        if e.code != 429:  # 429 = 请求太频繁，稍等重试一次
            raise
        time.sleep(1.5)
        return engine(text, target)


def _translate_chunk(chunk, target):
    lead, core, trail = re.match(r"(\s*)(.*?)(\s*)$", chunk, re.S).groups()
    if not core:
        return chunk
    first = _preferred["engine"]
    errors = []
    for engine in [first] + [e for e in ENGINES if e is not first]:
        try:
            result = _try_engine(engine, core, target)
            _preferred["engine"] = engine
            return lead + result + trail
        except Exception as e:  # noqa: BLE001
            name = engine.__name__.replace("translate_", "")
            errors.append(f"{name}: {e}")
    raise RuntimeError("翻译失败，请检查网络连接。\n" + "\n".join(errors))


def translate(text, target, progress=None):
    """翻译任意长度的文本。progress(已完成段数, 总段数) 用于显示进度。"""
    chunks = split_text(text)
    total = len(chunks)
    done = [0]
    lock = threading.Lock()

    def one(chunk):
        result = _translate_chunk(chunk, target)
        with lock:
            done[0] += 1
            if progress and total > 1:
                progress(done[0], total)
        return result

    if total == 1:
        return one(chunks[0])
    with ThreadPoolExecutor(WORKERS) as pool:
        return "".join(pool.map(one, chunks))
