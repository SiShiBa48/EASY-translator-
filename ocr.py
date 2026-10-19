"""调用 Windows 10/11 自带的 OCR（Windows.Media.Ocr）识别图片中的文字。

通过 Windows PowerShell 访问 WinRT 接口，无需额外安装任何组件。
"""

import base64
import os
import re
import subprocess
import tempfile

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
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if ($engine -eq $null) {
    $langs = [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages
    if ($langs.Count -gt 0) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($langs[0]) }
}
if ($engine -eq $null) { Write-Output '__NO_OCR_LANGUAGE__'; exit 0 }
$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
foreach ($line in $result.Lines) { Write-Output $line.Text }
$stream.Dispose()
"""

_ENCODED = base64.b64encode(_PS_SCRIPT.encode("utf-16-le")).decode("ascii")

_CJK = r"[　-〿぀-ヿ㐀-鿿가-힯＀-￯]"


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


def recognize(image):
    """识别 PIL Image 中的文字，返回字符串。失败时抛出 RuntimeError。"""
    # 小图放大后识别率更高
    if image.height < 60:
        scale = max(2, 60 // max(image.height, 1))
        image = image.resize((image.width * scale, image.height * scale))

    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        image.save(path)
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-EncodedCommand", _ENCODED],
            capture_output=True,
            timeout=30,
            env={**os.environ, "EASY_OCR_IMAGE": path},
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
    lines = out.splitlines()
    if lines and lines[0].strip() == "__NO_OCR_LANGUAGE__":
        raise RuntimeError(
            "系统中没有可用的文字识别语言。\n"
            "请到 Windows 设置 → 时间和语言 → 语言 中添加“中文(简体)”或“English”语言包。"
        )
    return _tidy(lines)
