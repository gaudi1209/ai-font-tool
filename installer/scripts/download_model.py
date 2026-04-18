# -*- coding: utf-8 -*-
"""模型下载工具 - 支持断点续传"""

import argparse
import hashlib
import os
import sys


# 下载源列表（按优先级）
DOWNLOAD_URLS = [
    # HuggingFace 镜像（国内可用）
    "https://hf-mirror.com/kaonashi/zi2zi-JiT/resolve/main/zi2zi-JiT-B-16.pth",
    # GitHub Release（备选）
    "https://github.com/kaonashi-tyc/zi2zi-JiT/releases/download/v1.0/zi2zi-JiT-B-16.pth",
]

EXPECTED_SIZE = 2_363_129_856  # 约 2.2GB


def download_with_progress(url, output_path):
    """支持断点续传的下载"""
    import urllib.request

    existing_size = 0
    if os.path.exists(output_path):
        existing_size = os.path.getsize(output_path)
        print(f"  已有文件 {existing_size / 1024 / 1024:.0f}MB，尝试断点续传...")

    headers = {"User-Agent": "Mozilla/5.0"}
    if existing_size > 0:
        headers["Range"] = f"bytes={existing_size}-"

    req = urllib.request.Request(url, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=30)
    except Exception as e:
        print(f"  连接失败: {e}")
        return False

    total_size = int(resp.headers.get("Content-Length", 0))
    if existing_size > 0 and resp.status == 206:
        total_size += existing_size  # 续传时 total = 已有 + 剩余
    elif existing_size > 0 and resp.status == 200:
        existing_size = 0  # 不支持续传，重新下载

    mode = "ab" if existing_size > 0 else "wb"
    downloaded = existing_size
    chunk_size = 1024 * 1024  # 1MB
    last_pct = -1

    with open(output_path, mode) as f:
        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)
            if total_size > 0:
                pct = int(downloaded / total_size * 100)
                if pct != last_pct and pct % 5 == 0:
                    print(f"  下载进度: {pct}% ({downloaded / 1024 / 1024:.0f}MB / {total_size / 1024 / 1024:.0f}MB)")
                    last_pct = pct

    final_size = os.path.getsize(output_path)
    print(f"  下载完成: {final_size / 1024 / 1024:.0f}MB")
    return True


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="下载 zi2zi-JiT 基础模型")
    parser.add_argument("--output", required=True, help="输出文件路径")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    for i, url in enumerate(DOWNLOAD_URLS):
        print(f"\n尝试下载源 {i + 1}/{len(DOWNLOAD_URLS)}: {url[:60]}...")
        try:
            if download_with_progress(url, args.output):
                final_size = os.path.getsize(args.output)
                if abs(final_size - EXPECTED_SIZE) < 1024 * 1024:  # 允许 1MB 误差
                    print("\n[OK] 模型下载并校验完成")
                    return 0
                else:
                    print(f"  文件大小异常 ({final_size} vs 预期 {EXPECTED_SIZE})，尝试下一个源...")
            else:
                print("  下载失败，尝试下一个源...")
        except Exception as e:
            print(f"  下载出错: {e}")

    print("\n[错误] 所有下载源均失败")
    print("请手动下载模型文件并放入 engine/models/ 目录")
    return 1


if __name__ == "__main__":
    sys.exit(main())
