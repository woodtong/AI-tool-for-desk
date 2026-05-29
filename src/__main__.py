"""
支持 python -m src 方式运行
"""
import sys
import os

script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from src.app import main

main()
