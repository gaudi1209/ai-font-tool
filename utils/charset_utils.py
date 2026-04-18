# -*- coding: utf-8 -*-
"""字符集工具 - 字体字符集计算"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fontTools.ttLib import TTFont

# 完整 CJK 范围（含所有扩展区 C-G、兼容区）
CJK_RANGES = [
    (0x4E00, 0x9FFF),    # CJK Unified Ideographs
    (0x3400, 0x4DBF),    # Extension A
    (0x20000, 0x2A6DF),  # Extension B
    (0x2A700, 0x2B73F),  # Extension C
    (0x2B740, 0x2B81F),  # Extension D
    (0x2B820, 0x2CEAF),  # Extension E
    (0x2CEB0, 0x2EBEF),  # Extension F
    (0x30000, 0x3134F),  # Extension G
    (0xF900, 0xFAFF),    # Compatibility Ideographs
    (0x2F800, 0x2FA1F),  # Compatibility Supplement
]


def is_cjk(cp):
    """判断码点是否为 CJK 汉字（含所有扩展区）"""
    for start, end in CJK_RANGES:
        if start <= cp <= end:
            return True
    return False


def get_font_chars(font_path):
    """获取字体中的所有汉字Unicode码点集合"""
    font = TTFont(font_path)
    cmap = font.getBestCmap()
    font.close()

    return {cp for cp in cmap.keys() if is_cjk(cp)}


def get_charset(charset_name):
    """获取标准字符集的码点集合"""
    # 常用字符集范围
    charsets = {
        "GB2312": _gb2312_chars(),
        "GBK": _gbk_chars(),
        "Big5": _big5_chars(),
    }
    return charsets.get(charset_name, set())


def get_missing_chars(font_path, charset_name):
    """计算字体相对于字符集的缺失字符"""
    font_chars = get_font_chars(font_path)
    charset = get_charset(charset_name)
    missing = sorted(charset - font_chars)
    return missing


def _gb2312_chars():
    """GB2312一级+二级汉字 (6763字)"""
    chars = set()
    # 一级汉字 3755字 (B0A1-D7F9)
    for b1 in range(0xB0, 0xD8):
        for b2 in range(0xA1, 0xFF):
            try:
                c = bytes([b1, b2]).decode('gb2312')
                chars.add(ord(c))
            except Exception:
                pass
    # 二级汉字 3008字 (D8A1-F7FE)
    for b1 in range(0xD8, 0xF8):
        for b2 in range(0xA1, 0xFF):
            try:
                c = bytes([b1, b2]).decode('gb2312')
                chars.add(ord(c))
            except Exception:
                pass
    return chars


def _gbk_chars():
    """GBK汉字 (约20902字)"""
    chars = set()
    for b1 in range(0x81, 0xFF):
        for b2 in range(0x40, 0xFF):
            if b2 == 0x7F:
                continue
            try:
                c = bytes([b1, b2]).decode('gbk')
                if is_cjk(ord(c)):
                    chars.add(ord(c))
            except Exception:
                pass
    return chars


def _big5_chars():
    """Big5常用汉字"""
    chars = set()
    for b1 in range(0xA1, 0xFA):
        for b2 in range(0x40, 0xFF):
            if b2 == 0x7F:
                continue
            try:
                c = bytes([b1, b2]).decode('big5')
                if is_cjk(ord(c)):
                    chars.add(ord(c))
            except Exception:
                pass
    return chars


def fontlab_filename(code, char=None):
    """FontLab命名：BMP=uniXXXX，扩展区=uXXXXX"""
    if code > 0xFFFF:
        name = f"u{code:05X}"
    else:
        name = f"uni{code:04X}"
    if char:
        name += f"_{char}"
    return name + ".png"


def split_into_groups(codes, group_size=500):
    """将码点列表分组"""
    groups = []
    for i in range(0, len(codes), group_size):
        groups.append(codes[i:i + group_size])
    return groups
