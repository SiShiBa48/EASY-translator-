# Easy Translator

极简翻译软件：上面输入，下面出译文。支持中文、英文等输入（自动识别），翻译成你选择的语言。

## 使用
- 在上方输入框打字，停顿约 0.7 秒自动翻译（或按 `Ctrl+Enter` 立即翻译）
- 右上角下拉框选择目标语言（会记住上次的选择和窗口大小）
- “复制译文”一键复制结果

### 截图翻译
- 点“截图翻译”按钮，或在任何地方按全局快捷键（默认 `Ctrl+Alt+Q`）
- 屏幕变暗后，用鼠标框选要翻译的文字（`Esc` 或右键取消）
- 识别出的文字会自动填进上方输入框并翻译
- 点“快捷键设置”可以改快捷键：直接按下想要的组合键，再点保存

文字识别使用 Windows 10/11 自带的 OCR，不联网、免费。系统里需要有对应的语言包（中文版 Windows 一般自带中文和英文）。

翻译优先使用 Google 翻译；连不上时自动改用 MyMemory（国内一般可直接访问）。需要联网。

## 获取 exe
**方式一（推荐）**：打开 GitHub 仓库的 **Actions** 页 → 最新一次 “Build Windows exe” → 页面底部 Artifacts 下载 `EasyTranslator`，解压得到 `EasyTranslator.exe`，双击即可运行。

**方式二**：在 Windows 上安装 Python 3，双击 `build.bat`，生成 `dist\EasyTranslator.exe`。

也可以直接运行：`python translator.py`
