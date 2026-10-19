@echo off
REM 在 Windows 上本地打包成 exe（需要先安装 Python 3）
pip install pyinstaller -r requirements.txt
pyinstaller --onefile --windowed --name EasyTranslator --hidden-import pystray._win32 translator.py
echo.
echo 完成！exe 位于 dist\EasyTranslator.exe
pause
