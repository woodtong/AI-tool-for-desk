"""
AI 桌面助手 - 入口文件

使用方式:
    python main.py

首次运行会自动弹出 AI 模型选择条幅。
配置文件和 API Key 通过系统托盘菜单设置。

快捷键（可在 config.json 中自定义）:
    Win+Shift+F — 唤出 AI 选择条幅
    Win+Shift+Z — 截图并发送给 AI
    Win+Shift+X — 选取文字并发送给 AI
"""
import sys
import os
import logging

# 确保项目根目录在 Python 路径中
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


def main():
    """启动 AI 桌面助手"""
    from src.app import main as app_main
    app_main()


if __name__ == "__main__":
    main()
