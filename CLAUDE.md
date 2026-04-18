# CLAUDE.md - AI字体生产工具

## 项目概述

基于 zi2zi-JiT 的 AI 字体训练与生成 Web 工具。Flask 后端 + 原生前端，包含三个模块：模型训练、字库生字、OCR 识别。

## CJK 扩展区字符支持（强制规则）

**所有输入框、文本框、输出结果必须完整支持 CJK 扩展区字符（CJK Extension B-G）。**

### Python 端

- **统一使用 `is_cjk()` 函数**（定义在 `utils/charset_utils.py`）判断汉字，不要手写范围判断
- 完整 CJK 范围包括：
  - `U+4E00-U+9FFF` CJK Unified Ideographs
  - `U+3400-U+4DBF` Extension A
  - `U+20000-U+2A6DF` Extension B
  - `U+2A700-U+2B73F` Extension C
  - `U+2B740-U+2B81F` Extension D
  - `U+2B820-U+2CEAF` Extension E
  - `U+2CEB0-U+2EBEF` Extension F
  - `U+30000-U+3134F` Extension G
  - `U+F900-U+FAFF` Compatibility Ideographs
  - `U+2F800-U+2FA1F` Compatibility Supplement
- **禁止**使用 `'\u4e00' <= c <= '\u9fff'` 这种窄范围判断
- `chr(codepoint)` 对扩展区码点（>0xFFFF）正常工作，无需特殊处理
- 文件名中包含扩展区汉字：`f"uni{code:04X}_{char}.png"` 或 `f"u{code:05X}_{char}.png"`

### JavaScript 端

- **禁止**使用 `.split('')` 拆分包含扩展区字符的字符串，它会把 surrogate pair 拆成两个乱码
- 正确拆分字符：`[...str]` 或 `Array.from(str)` — 按 code point 迭代
- 计算字符数：`Array.from(str).length`，不要用 `str.length`（扩展区字符 str.length=2）
- 构造字符：`String.fromCodePoint(code)`，不要用 `String.fromCharCode()`

### 字体渲染

- 扩展区字符并非所有字体都支持，渲染前应检查字体的 cmap 是否包含该码点
- `GlyphRenderer.render()` 可能对不支持的字符返回空白白图而非 None，需检查像素值

## 关键文件

| 文件 | 用途 |
|------|------|
| `app.py` | Flask 主应用，API 路由 |
| `config.py` | 全局配置（路径、默认参数） |
| `utils/train_manager.py` | 训练进程管理（数据准备、训练启停、测试生成） |
| `utils/generate_manager.py` | 字库生字进程管理 |
| `utils/ocr_manager.py` | OCR 识别进程管理 |
| `utils/charset_utils.py` | 字符集工具（CJK 判断、字符集计算、缺失字符） |
| `templates/*.html` | 页面模板 |
| `static/js/*.js` | 前端逻辑 |

## 技术栈

- 后端：Python 3 + Flask + fontTools + Pillow
- 训练引擎：zi2zi-JiT（PyTorch + LoRA fine-tuning）
- 前端：原生 HTML/CSS/JS，无框架
- 字体渲染：fontTools TTFont + PIL ImageFont

## 编码规范

- 所有文件 UTF-8 编码
- Python 脚本开头：`sys.stdout.reconfigure(encoding='utf-8')`
