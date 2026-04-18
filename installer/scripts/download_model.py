# -*- coding: utf-8 -*-
"""模型下载工具 - 支持分片下载、断点续传、多源 fallback"""

import argparse
import os
import sys

RELEASE_BASE = "https://github.com/gaudi1209/ai-font-tool/releases/download/v1.0"

# 分片文件列表（B-16 模型因超过 GitHub 2GB 限制被拆分）
PART_FILES = [
    ("zi2zi-JiT-B-16.pth.part_aa", 1_992_294_400),
    ("zi2zi-JiT-B-16.pth.part_ab", 314_042_141),
]

EXPECTED_SIZE = 2_363_129_856  # 合并后约 2.2GB

# 备选下载源（单文件）
FALLBACK_URLS = [
    "https://hf-mirror.com/kaonashi/zi2zi-JiT/resolve/main/zi2zi-JiT-B-16.pth",
]


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


def download_split_model(output_path):
    """分片下载并合并"""
    part_dir = os.path.dirname(output_path)

    # 逐个下载分片
    for i, (part_name, expected_part_size) in enumerate(PART_FILES):
        part_path = os.path.join(part_dir, part_name)
        part_url = f"{RELEASE_BASE}/{part_name}"

        # 检查分片是否已下载完成
        if os.path.exists(part_path):
            actual_size = os.path.getsize(part_path)
            if abs(actual_size - expected_part_size) < 1024 * 1024:
                print(f"  分片 {i+1}/{len(PART_FILES)} 已存在，跳过")
                continue
            else:
                print(f"  分片 {i+1}/{len(PART_FILES)} 大小异常，重新下载")
                os.remove(part_path)

        print(f"\n  下载分片 {i+1}/{len(PART_FILES)}: {part_name}")
        if not download_with_progress(part_url, part_path):
            return False

        # 校验分片大小
        actual_size = os.path.getsize(part_path)
        if abs(actual_size - expected_part_size) > 5 * 1024 * 1024:
            print(f"  分片大小异常: {actual_size} vs 预期 {expected_part_size}")
            return False

    # 合并分片
    print(f"\n  合并分片 -> {os.path.basename(output_path)}")
    with open(output_path, "wb") as out:
        for part_name, _ in PART_FILES:
            part_path = os.path.join(part_dir, part_name)
            with open(part_path, "rb") as pf:
                while True:
                    chunk = pf.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
            print(f"    已合并: {part_name}")

    # 校验合并后大小
    final_size = os.path.getsize(output_path)
    print(f"  合并完成: {final_size / 1024 / 1024:.0f}MB")

    # 删除分片文件
    for part_name, _ in PART_FILES:
        part_path = os.path.join(part_dir, part_name)
        if os.path.exists(part_path):
            os.remove(part_path)
            print(f"  已删除分片: {part_name}")

    return True


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="下载 zi2zi-JiT 基础模型")
    parser.add_argument("--output", required=True, help="输出文件路径")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    # 如果最终文件已存在且大小正确，跳过下载
    if os.path.exists(args.output):
        actual_size = os.path.getsize(args.output)
        if abs(actual_size - EXPECTED_SIZE) < 5 * 1024 * 1024:
            print(f"模型文件已存在 ({actual_size / 1024 / 1024:.0f}MB)，跳过下载")
            return 0
        else:
            print(f"模型文件大小异常，重新下载")

    # 方案一：从 GitHub Release 分片下载
    print("=" * 50)
    print("方案一：GitHub Release 分片下载")
    print("=" * 50)
    try:
        if download_split_model(args.output):
            final_size = os.path.getsize(args.output)
            if abs(final_size - EXPECTED_SIZE) < 5 * 1024 * 1024:
                print("\n[OK] 模型下载并校验完成")
                return 0
            else:
                print(f"  合并后大小异常 ({final_size} vs 预期 {EXPECTED_SIZE})")
                if os.path.exists(args.output):
                    os.remove(args.output)
    except Exception as e:
        print(f"  分片下载出错: {e}")

    # 方案二：备选源单文件下载
    for i, url in enumerate(FALLBACK_URLS):
        print(f"\n{'=' * 50}")
        print(f"方案二：备选源下载 {i+1}/{len(FALLBACK_URLS)}")
        print(f"{'=' * 50}")
        print(f"  URL: {url[:60]}...")
        try:
            if download_with_progress(url, args.output):
                final_size = os.path.getsize(args.output)
                if abs(final_size - EXPECTED_SIZE) < 5 * 1024 * 1024:
                    print("\n[OK] 模型下载并校验完成")
                    return 0
                else:
                    print(f"  文件大小异常 ({final_size} vs 预期 {EXPECTED_SIZE})，尝试下一个源...")
                    if os.path.exists(args.output):
                        os.remove(args.output)
        except Exception as e:
            print(f"  下载出错: {e}")

    print("\n[错误] 所有下载源均失败")
    print("请手动下载模型文件并放入 engine/models/ 目录")
    print(f"  分片下载地址:")
    for part_name, _ in PART_FILES:
        print(f"    {RELEASE_BASE}/{part_name}")
    print(f"  下载后使用命令合并:")
    print(f"    copy /b {PART_FILES[0][0]}+{PART_FILES[1][0]} zi2zi-JiT-B-16.pth")
    return 1


if __name__ == "__main__":
    sys.exit(main())
