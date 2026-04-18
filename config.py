# -*- coding: utf-8 -*-
"""AI字体生产工具 - 配置文件"""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ZI2ZI_DIR = r"D:\Claudecode\字体训练\zi2zi-JiT-main"

# Python 环境
ZI2ZI_PYTHON = r"C:\Users\chenlin\.conda\envs\zi2zi-jit\python.exe"
OCR_PYTHON = r"D:\Claudecode\paddle-ocr\venv\Scripts\python.exe"
SYSTEM_PYTHON = "python"

# 默认路径
DEFAULT_BASE_CHECKPOINT = os.path.join(ZI2ZI_DIR, "models", "zi2zi-JiT-B-16.pth")
DEFAULT_SOURCE_FONT = os.path.join(ZI2ZI_DIR, "data", "font", "WenJinMinchoP0-Regular.ttf")
DEFAULT_REF_FONT = r"C:\Users\chenlin\Desktop\2026工作文件\高迪书法_行书V5\OpenType-TT\高迪书法_行书V5-Regular.260415-0920.ttf"
DEFAULT_RUN_DIR = os.path.join(ZI2ZI_DIR, "run")

# 训练默认参数
TRAIN_DEFAULTS = {
    "model": "JiT-B/16",
    "epochs": 200,
    "batch_size": 64,
    "lora_r": 32,
    "lora_alpha": 32,
    "lora_targets": "qkv,proj,w12,w3",
    "cfg": 2.6,
    "sampling_method": "heun",
    "num_sampling_steps": 50,
    "num_fonts": 1000,
    "num_chars": 200000,
    "max_chars_per_font": 10000,
    "num_workers": 0,
}

# 生成默认参数
GENERATE_DEFAULTS = {
    "multiplier": 5,
    "max_rounds": 10,
    "confidence_threshold": 0.5,
    "cfg": 4.0,
    "sampling_method": "heun",
    "num_sampling_steps": 50,
    "batch_size": 64,
    "resolution": 256,
    "ref_size": 128,
}

# 字符集定义
CHARSET_SIZES = {
    "GB2312": 6763,
    "GBK": 20902,
    "Big5": 13053,
}

# 参考字符
REF_CHARS = ['永', '和', '之', '道', '心', '人', '大', '天']

# Flask 配置
HOST = "0.0.0.0"
PORT = 7550
DEBUG = True
