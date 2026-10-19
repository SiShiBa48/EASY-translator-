"""调用 Windows 10/11 自带的 OCR（Windows.Media.Ocr）识别图片中的文字。

通过 Windows PowerShell 访问 WinRT 接口，无需额外安装任何组件。
"""

import base64
import os
import re
import subprocess
import tempfile

from PIL import Image, ImageOps

# 显示名称 -> 语言前缀（逗号分隔，按顺序匹配系统已安装的识别语言）
OCR_LANGUAGES = {
    "自动（中文/英文）": "auto",
    "中文（简体）": "zh-Hans,zh-CN,zh-SG",
    "中文（繁體）": "zh-Hant,zh-TW,zh-HK,zh-MO",
    "英语": "en",
    "日语": "ja",
    "韩语": "ko",
    "法语": "fr",
    "德语": "de",
    "西班牙语": "es",
    "俄语": "ru",
    "葡萄牙语": "pt",
    "意大利语": "it",
}
# 自动模式：同时用“中日韩里第一个可用的”和“英语”各识别一次，再挑结果
_AUTO_GROUPS = "zh-Hans,zh-CN,zh-SG,zh-Hant,zh-TW,zh-HK,zh,ja,ko|en"

MAX_DIM = 4000  # 送去识别的图片最长边（Windows OCR 对超大图片会报错）

_PS_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $type) {
    $task = $asTask.MakeGenericMethod($type).Invoke($null, @($op))
    $task.Wait(-1) | Out-Null
    $task.Result
}
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($env:EASY_OCR_IMAGE)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])

function Run-Ocr($engine, $tag) {
    Write-Output ('##' + $tag)
    $r = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
    foreach ($line in $r.Lines) { Write-Output $line.Text }
}

$avail = [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages
$picked = @()
foreach ($group in $env:EASY_OCR_GROUPS.Split('|')) {
    $found = $null
    foreach ($prefix in $group.Split(',')) {
        $found = $avail | Where-Object { $_.LanguageTag -like ($prefix + '*') } | Select-Object -First 1
        if ($found) { break }
    }
    if ($found) { $picked += $found }
}
if ($picked.Count -eq 0) {
    if ($env:EASY_OCR_STRICT -eq '1') {
        Write-Output ('__LANG_MISSING__ ' + (($avail | ForEach-Object { $_.DisplayName }) -join ', '))
        exit 0
    }
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    if ($engine -eq $null) { Write-Output '__NO_OCR_LANGUAGE__'; exit 0 }
    Run-Ocr $engine 'profile'
} else {
    foreach ($lang in $picked) {
        Run-Ocr ([Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($lang)) $lang.LanguageTag
    }
}
$stream.Dispose()
"""

_ENCODED = base64.b64encode(_PS_SCRIPT.encode("utf-16-le")).decode("ascii")

_CJK = r"[　-〿぀-ヿ㐀-鿿가-힯＀-￯]"

_INSTALL_HINT = (
    "请到 Windows 设置 → 时间和语言 → 语言和区域 → 添加语言，安装对应语言"
    "（安装时勾选“光学字符识别”或“基本键入”），然后重新截图。"
)


def _tidy(lines):
    """把多行合并成一段，并去掉 OCR 在汉字之间插入的空格。"""
    text = ""
    for line in (l.strip() for l in lines):
        if not line:
            continue
        if text and not (re.search(_CJK + "$", text) and re.match(_CJK, line)):
            text += " "
        text += line
    return re.sub(f"(?<={_CJK}) +(?={_CJK})", "", text)


def _cjk_ratio(text):
    chars = re.sub(r"\s", "", text)
    return len(re.findall(_CJK, chars)) / len(chars) if chars else 0.0


def prepare(image):
    """放大小字、加白边，提高识别率。"""
    image = image.convert("RGB")
    w, h = image.size
    scale = 3 if h < 80 else 2
    scale = min(scale, MAX_DIM / max(w, h))
    if scale != 1:
        image = image.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    # 用左上角颜色当背景加一圈边，文字紧贴边缘时识别更稳
    return ImageOps.expand(image, border=20, fill=image.getpixel((0, 0)))


def _run(image, groups, strict):
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        image.save(path)
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-EncodedCommand", _ENCODED],
            capture_output=True,
            timeout=30,
            env={**os.environ, "EASY_OCR_IMAGE": path, "EASY_OCR_GROUPS": groups,
                 "EASY_OCR_STRICT": "1" if strict else "0"},
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

    out = proc.stdout.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip() or out.strip()
        raise RuntimeError("文字识别失败：" + err[-500:])
    first = out.lstrip().split("\n", 1)[0].strip()
    if first.startswith("__LANG_MISSING__"):
        installed = first[len("__LANG_MISSING__"):].strip() or "无"
        raise RuntimeError(f"系统中没有安装这个识别语言。\n当前已安装：{installed}\n\n{_INSTALL_HINT}")
    if first == "__NO_OCR_LANGUAGE__":
        raise RuntimeError("系统中没有可用的文字识别语言。\n\n" + _INSTALL_HINT)

    results = []  # [(语言标签, 行列表)]
    for line in out.splitlines():
        if line.startswith("##"):
            results.append((line[2:].strip(), []))
        elif results:
            results[-1][1].append(line)
    return results


def recognize(image, language="auto"):
    """识别 PIL Image 中的文字。language 为 OCR_LANGUAGES 中的值。失败时抛出 RuntimeError。"""
    image = prepare(image)
    if language == "auto":
        results = _run(image, _AUTO_GROUPS, strict=False)
    else:
        results = _run(image, language, strict=True)
    texts = [_tidy(lines) for _tag, lines in results]
    if len(texts) == 2:
        # 第一个是中日韩识别结果，第二个是英文识别结果：内容以中日韩文字为主就用第一个
        return texts[0] if _cjk_ratio(texts[0]) >= 0.15 else texts[1]
    return texts[0] if texts else ""
