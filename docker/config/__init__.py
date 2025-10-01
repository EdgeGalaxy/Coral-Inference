# 设置Python路径，使core模块可以被正确导入
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
