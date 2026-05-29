# AI 桌面助手

一个 Windows 桌面工具，通过全局快捷键快速调用 AI 模型，支持截图分析和文字选取。

## 功能

| 快捷键 | 功能 | 说明 |
|--------|------|------|
| Win+Shift+F | 唤醒条幅 | 选择要使用的 AI 模型 |
| Win+Shift+Z | 截图 | 框选屏幕区域发送给 AI 分析 |
| Win+Shift+X | 文字选取 | 将选中的文字发送给 AI |

> 快捷键可在 `config.json` 中自定义。

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 启动
python main.py
```

第一次启动时会显示 AI 模型选择条幅，选择模型后可通过系统托盘菜单配置 API Key。

## 系统托盘

- **左键 / 双击**: 切换对话窗口
- **右键菜单**:
  - 显示/隐藏对话窗口
  - 选择 AI 模型
  - 配置 API Key
  - 退出

## 支持的 AI 模型

| 模型 | 支持图片 | 配置方式 |
|------|---------|---------|
| OpenAI (GPT-4o等) | 是 | 在 `config.json` 中填入 API Key |
| DeepSeek | 否 | 在 `config.json` 中填入 API Key |
| 自定义 API | 依赖模型 | 配置 base_url + api_key |

## 项目结构

```
ai-tool-for-desk/
├── main.py                    # 入口文件
├── pyproject.toml             # 项目元数据
├── requirements.txt           # 依赖清单
├── config.json                # 运行时配置（自动生成）
├── src/
│   ├── app.py                 # 应用主类，组件编排
│   ├── banner.py              # AI 模型选择条幅
│   ├── chat_window.py         # 对话窗口
│   ├── config_manager.py      # 配置读写
│   ├── hotkey_manager.py      # 全局热键
│   ├── screenshot.py          # 截图模块
│   ├── screenshot_overlay.py  # 截图选区 UI
│   ├── text_capture.py        # 文字选取
│   └── ai_providers/
│       ├── adapter.py         # AI API 适配器
│       └── manager.py         # AI 提供者管理
└── .gitignore
```

## 配置

编辑 `config.json`（首次运行自动生成）:

```json
{
  "hotkeys": {
    "show_banner":   { "mod": "win+shift", "key": "f" },
    "screenshot":    { "mod": "win+shift", "key": "z" },
    "text_capture":  { "mod": "win+shift", "key": "x" }
  },
  "providers": [
    {
      "id": "openai",
      "name": "OpenAI",
      "base_url": "https://api.openai.com/v1",
      "model": "gpt-4o"
    }
  ]
}
```
