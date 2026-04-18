# -*- coding: utf-8 -*-
"""训练进程管理器 - 管理zi2zi-JiT训练subprocess"""

import os
import sys
import subprocess
import threading
import time
import json
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config import ZI2ZI_DIR, ZI2ZI_PYTHON


def _open_font(path):
    """安全打开字体文件，自动处理 .ttc 集合字体"""
    from fontTools.ttLib import TTFont
    try:
        return TTFont(path)
    except Exception:
        return TTFont(path, fontNumber=0)


class TrainManager:
    def __init__(self):
        self.process = None
        self.log_file = None
        self.log_path = None
        self.status = "idle"  # idle, preparing, training, completed, error
        self.error_message = ""
        self.start_time = None
        self.current_epoch = 0
        self.total_epochs = 0
        self.current_loss = 0
        self.current_lr = 0
        self._lock = threading.Lock()
        self.last_params = {}  # 保存上次训练/准备的参数，供继续训练和测试生成使用

    def prepare_data(self, data_dir, ref_font, source_font, resolution=256, ref_size=128, char_count=None):
        """准备训练数据 - 创建复合图片目录和test.npz

        Args:
            char_count: 取字数量，None表示全部，数字表示限制数量
        """
        self.status = "preparing"
        self.error_message = ""
        self.start_time = time.time()

        try:
            import numpy as np
            from PIL import Image
            from fontTools.ttLib import TTFont

            sys.path.insert(0, ZI2ZI_DIR)
            from data_processing.font_utils import GlyphRenderer as ZGlyphRenderer

            # 获取参考字体中的汉字
            font = _open_font(ref_font)
            cmap = font.getBestCmap()
            font.close()

            han_chars = []
            for cp in cmap.keys():
                if (0x4E00 <= cp <= 0x9FFF) or (0x3400 <= cp <= 0x4DBF) or (0x20000 <= cp <= 0x2A6DF) or (0x2A700 <= cp <= 0x2B73F) or (0x2B740 <= cp <= 0x2B81F) or (0x2B820 <= cp <= 0x2CEAF) or (0x2CEB0 <= cp <= 0x2EBEF) or (0x30000 <= cp <= 0x3134F):
                    han_chars.append(chr(cp))

            if not han_chars:
                self.status = "error"
                self.error_message = "参考字体中没有找到汉字字符"
                return {"success": False, "error": self.error_message}

            # 按数量限制取字
            if char_count is not None and char_count > 0:
                han_chars = han_chars[:char_count]

            # 创建带字库名+时间戳的新目录，不同字库自动分目录
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            font_stem = os.path.splitext(os.path.basename(ref_font))[0]
            data_dir = os.path.join(data_dir, f"train_{font_stem}_{timestamp}")
            os.makedirs(data_dir, exist_ok=True)

            # 创建数据目录结构
            output_data_dir = os.path.join(data_dir, "001_font")
            os.makedirs(output_data_dir, exist_ok=True)

            ref_renderer = ZGlyphRenderer(ref_font, ref_size)
            source_renderer = ZGlyphRenderer(source_font, resolution)
            target_renderer = ZGlyphRenderer(ref_font, resolution)

            ref_chars = ['永', '和', '之', '道', '心', '人', '大', '天']

            success = 0
            for char in han_chars:
                codepoint = ord(char)
                try:
                    target_img = target_renderer.render(codepoint)
                    source_img = source_renderer.render(codepoint)
                    if target_img is None or source_img is None:
                        continue

                    if isinstance(target_img, np.ndarray):
                        target_img = Image.fromarray(target_img)
                    if isinstance(source_img, np.ndarray):
                        source_img = Image.fromarray(source_img)

                    composite = Image.new('RGB', (1024, 256), (255, 255, 255))
                    source_resized = source_img.resize((resolution, resolution), Image.Resampling.LANCZOS)
                    composite.paste(source_resized, (0, 0))
                    target_resized = target_img.resize((resolution, resolution), Image.Resampling.LANCZOS)
                    composite.paste(target_resized, (256, 0))

                    for grid_idx in range(2):
                        ref_grid = Image.new('RGB', (256, 256), (255, 255, 255))
                        for j, ref_char in enumerate(ref_chars[grid_idx*4:(grid_idx+1)*4]):
                            ref = ref_renderer.render(ord(ref_char))
                            if ref is not None:
                                if isinstance(ref, np.ndarray):
                                    ref = Image.fromarray(ref)
                                ref = ref.resize((128, 128), Image.Resampling.LANCZOS)
                                x = (j % 2) * 128
                                y = (j // 2) * 128
                                ref_grid.paste(ref, (x, y))
                        composite.paste(ref_grid, (512 + grid_idx * 256, 0))

                    # 使用连续编号命名，与训练脚本兼容
                    composite.save(os.path.join(output_data_dir, f"{success:05d}_{char}.png"))
                    success += 1
                except Exception:
                    continue

            # 创建test.npz
            test_npz_path = os.path.join(data_dir, "test.npz")
            self._create_test_npz(output_data_dir, test_npz_path, ref_font, source_font, resolution, ref_size)

            self.status = "idle"
            self.last_params = {
                "output_dir": data_dir,
                "ref_font": ref_font,
                "source_font": source_font,
                "char_count": success,
            }
            return {
                "success": True,
                "char_count": success,
                "data_dir": data_dir,
                "test_npz": test_npz_path
            }

        except Exception as e:
            self.status = "error"
            self.error_message = str(e)
            return {"success": False, "error": str(e)}

    def _create_test_npz(self, data_dir, output_path, ref_font, source_font, resolution, ref_size):
        """创建测试npz文件"""
        import numpy as np
        from PIL import Image

        sys.path.insert(0, ZI2ZI_DIR)
        from data_processing.font_utils import GlyphRenderer

        ref_renderer = GlyphRenderer(ref_font, ref_size)
        source_renderer = GlyphRenderer(source_font, resolution)

        ref_img = ref_renderer.render(ord('永'))
        ref_array = np.array(ref_img.resize((ref_size, ref_size), Image.Resampling.LANCZOS))
        ref_array = ref_array.transpose(2, 0, 1)

        font_labels, char_labels, style_images, content_images, unicode_labels = [], [], [], [], []

        # 取前50个字符做测试
        files = sorted([f for f in os.listdir(data_dir) if f.endswith('.png')])[:50]
        for idx, f in enumerate(files):
            # 文件名格式: 00000_一.png → 提取字符获取码点
            parts = f.replace('.png', '').split('_', 1)
            char_name = parts[1] if len(parts) > 1 else ''
            codepoint = ord(char_name[0]) if char_name else 0
            src_img = source_renderer.render(codepoint)
            if src_img is None:
                continue
            src_array = np.array(src_img.resize((resolution, resolution), Image.Resampling.LANCZOS))
            src_array = src_array.transpose(2, 0, 1)

            font_labels.append(0)
            char_labels.append(idx)
            style_images.append(ref_array)
            content_images.append(src_array)
            unicode_labels.append(codepoint)

        np.savez(output_path,
                 font_labels=np.array(font_labels),
                 char_labels=np.array(char_labels),
                 style_images=np.array(style_images),
                 content_images=np.array(content_images),
                 unicode_labels=np.array(unicode_labels),
                 num_original_samples=np.array(len(font_labels)))

    def start_training(self, params):
        """启动训练进程"""
        if self.process and self.process.poll() is None:
            return {"success": False, "error": "训练正在进行中"}

        self.status = "training"
        self.error_message = ""
        self.current_epoch = 0
        self.current_loss = 0
        self.current_lr = 0
        self.start_time = time.time()
        self.total_epochs = params.get('epochs', 400)

        # 日志文件（放在 output_dir 的同级目录，避免被训练脚本当作数据目录）
        log_dir = os.path.join(os.path.dirname(params['output_dir']), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        self.log_path = os.path.join(log_dir, 'training.log')
        self.log_file = open(self.log_path, 'w', encoding='utf-8')

        # 构建训练命令 - 检查是否有 checkpoint 可断点续训
        script = os.path.join(ZI2ZI_DIR, "lora_finetune_jit.py")
        output_dir = params['output_dir']
        checkpoint_path = os.path.join(output_dir, 'checkpoint-last.pth')

        cmd = [
            ZI2ZI_PYTHON, script,
            "--data_path", params['data_path'],
            "--test_npz_path", params['test_npz_path'],
            "--output_dir", output_dir,
        ]
        # 断点续训：output_dir 有 checkpoint 则 resume，否则从头开始
        if os.path.exists(checkpoint_path):
            cmd.extend(["--resume", checkpoint_path])
            # 读取 checkpoint 中的 epoch，确保 total_epochs > start_epoch
            try:
                import torch
                ckpt = torch.load(checkpoint_path, map_location='cpu', weights_only=False)
                ckpt_epoch = ckpt.get('epoch', -1)
                del ckpt
                if ckpt_epoch >= 0 and self.total_epochs <= ckpt_epoch:
                    # 自动调整 total_epochs = checkpoint_epoch + addEpochs
                    add_epochs = params.get('add_epochs', 50)
                    self.total_epochs = ckpt_epoch + 1 + add_epochs
                    print(f"[TrainManager] Adjusted total_epochs to {self.total_epochs} (checkpoint epoch={ckpt_epoch})")
            except Exception as e:
                print(f"[TrainManager] Warning: could not read checkpoint epoch: {e}")
        else:
            cmd.extend(["--base_checkpoint", params['base_checkpoint']])

        cmd.extend([
            "--model", params.get('model', 'JiT-B/16'),
            "--num_fonts", str(params.get('num_fonts', 1000)),
            "--num_chars", str(params.get('num_chars', 200000)),
            "--max_chars_per_font", str(params.get('max_chars_per_font', 10000)),
            "--lora_r", str(params.get('lora_r', 32)),
            "--lora_alpha", str(params.get('lora_alpha', 32)),
            "--lora_targets", params.get('lora_targets', 'qkv,proj,w12,w3'),
            "--epochs", str(self.total_epochs),
            "--batch_size", str(params.get('batch_size', 64)),
            "--cfg", str(params.get('cfg', 2.6)),
            "--sampling_method", params.get('sampling_method', 'heun'),
            "--num_sampling_steps", str(params.get('num_sampling_steps', 50)),
            "--num_workers", str(params.get('num_workers', 0)),
        ])

        self.process = subprocess.Popen(
            cmd, stdout=self.log_file, stderr=subprocess.STDOUT,
            cwd=ZI2ZI_DIR
        )

        # 保存训练参数供继续训练和测试生成使用
        self.last_params = {
            "output_dir": output_dir,
            "ref_font": params.get('ref_font', ''),
            "source_font": params.get('source_font', ''),
            "data_path": params.get('data_path', ''),
            "test_npz_path": params.get('test_npz_path', ''),
            "base_checkpoint": params.get('base_checkpoint', ''),
            "epochs": self.total_epochs,
            "batch_size": params.get('batch_size', 64),
            "lora_r": params.get('lora_r', 32),
            "lora_alpha": params.get('lora_alpha', 32),
            "cfg": params.get('cfg', 2.6),
            "num_fonts": params.get('num_fonts', 1000),
            "num_chars": params.get('num_chars', 200000),
            "max_chars_per_font": params.get('max_chars_per_font', 10000),
        }

        # 后台读取日志
        thread = threading.Thread(target=self._read_output, daemon=True)
        thread.start()

        return {"success": True, "message": "训练已启动"}

    def _read_output(self):
        """后台从日志文件读取训练输出"""
        import io
        try:
            # 关闭写入用的 log_file，改用读取模式打开
            log_path = self.log_path
            self.log_file.close()
            self.log_file = None

            last_pos = 0
            while self.process.poll() is None:
                with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                    f.seek(last_pos)
                    for line in f:
                        # 解析epoch和loss
                        # 格式: Epoch: [30]  [11/12]  或  Epoch: [30] Total time
                        epoch_match = re.search(r'Epoch:\s+\[(\d+)\]', line)
                        if epoch_match:
                            self.current_epoch = int(epoch_match.group(1)) + 1

                        loss_match = re.search(r'loss[:\s]+([\d.]+)', line, re.IGNORECASE)
                        if loss_match:
                            self.current_loss = float(loss_match.group(1))

                        lr_match = re.search(r'lr[:\s]+([\d.e-]+)', line, re.IGNORECASE)
                        if lr_match:
                            self.current_lr = float(lr_match.group(1))
                    last_pos = f.tell()
                time.sleep(2)

            self.process.wait()

            if self.process.returncode == 0:
                self.status = "completed"
            else:
                self.status = "error"
                self.error_message = f"训练进程退出，返回码: {self.process.returncode}"

        except Exception as e:
            self.status = "error"
            self.error_message = str(e)
        finally:
            if self.log_file:
                self.log_file.close()
                self.log_file = None

    def stop_training(self):
        """停止训练"""
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.status = "idle"
            return {"success": True, "message": "训练已停止"}
        return {"success": False, "error": "没有正在运行的训练"}

    def test_generate(self, output_dir, ref_font, source_font, num_chars=20, resolution=256, ref_size=128):
        """用训练完成的模型快速生成测试字符（20已有 + 20新字）"""
        import numpy as np
        from PIL import Image

        sys.path.insert(0, ZI2ZI_DIR)
        from data_processing.font_utils import GlyphRenderer

        checkpoint_path = os.path.join(output_dir, 'checkpoint-last.pth')
        if not os.path.exists(checkpoint_path):
            return {"success": False, "error": "未找到 checkpoint-last.pth，请先完成训练"}

        # 读取训练字符列表
        font_dir = os.path.join(output_dir, '001_font')
        if not os.path.isdir(font_dir):
            return {"success": False, "error": "数据目录不存在"}

        train_chars = set()
        for f in os.listdir(font_dir):
            if f.endswith('.png') and '_' in f:
                char = f.split('_', 1)[1].replace('.png', '')
                if char:
                    train_chars.add(char)
        train_chars = sorted(train_chars, key=lambda c: ord(c))

        if not train_chars:
            return {"success": False, "error": "训练数据中没有字符"}

        # 获取字体所有CJK字符，找"新字"（不在训练集中的）
        from fontTools.ttLib import TTFont
        font = _open_font(ref_font)
        cmap = font.getBestCmap() or {}
        font.close()

        # 同时检查 source_font 的 cmap
        src_font_obj = _open_font(source_font)
        src_cmap = src_font_obj.getBestCmap() or {}
        src_font_obj.close()

        # 预过滤 train_chars：只保留两个字体 cmap 都有的字符
        train_chars = [ch for ch in train_chars if ord(ch) in cmap and ord(ch) in src_cmap]

        all_cjk = []
        for cp in sorted(cmap.keys()):
            if (0x4E00 <= cp <= 0x9FFF) or (0x3400 <= cp <= 0x4DBF) or (0x20000 <= cp <= 0x2A6DF) or (0x2A700 <= cp <= 0x2B73F) or (0x2B740 <= cp <= 0x2B81F) or (0x2B820 <= cp <= 0x2CEAF) or (0x2CEB0 <= cp <= 0x2EBEF) or (0x30000 <= cp <= 0x3134F):
                ch = chr(cp)
                if ch not in train_chars and ord(ch) in src_cmap:
                    all_cjk.append(ch)

        # 创建渲染器（提前，用于预验证）
        source_renderer = GlyphRenderer(source_font, resolution)
        target_renderer = GlyphRenderer(ref_font, resolution)
        ref_renderer = GlyphRenderer(ref_font, ref_size)
        # 扩展区 fallback 渲染器
        ext_font_path = r'C:\Windows\Fonts\simsunb.ttf'
        ext_renderer = GlyphRenderer(ext_font_path, resolution) if os.path.exists(ext_font_path) else None

        # cmap 检查：准确判断字符是否在字体中
        src_cmap = set(src_cmap.keys())  # 复用前面已加载的 src_cmap
        ext_cmap_set = set()
        if ext_renderer and os.path.exists(ext_font_path):
            try:
                ext_tt = TTFont(ext_font_path)
                ext_cmap_set = set((ext_tt.getBestCmap() or {}).keys())
                ext_tt.close()
            except Exception:
                pass

        def _render_source(codepoint):
            """渲染源字符，source font cmap 无则 fallback 到扩展区字体"""
            renderer = source_renderer if codepoint in src_cmap else ext_renderer
            if renderer is None:
                return None
            img = renderer.render(codepoint)
            if img is None:
                return None
            arr = np.array(img.resize((resolution, resolution), Image.Resampling.LANCZOS))
            if np.mean(arr) > 250:
                return None
            return img

        def _can_render(codepoint):
            """验证两个字体都能渲染出非空白图片"""
            src = _render_source(codepoint)
            if src is None:
                return False
            tgt = target_renderer.render(codepoint)
            if tgt is None:
                return False
            tgt_arr = np.array(tgt.resize((resolution, resolution), Image.Resampling.LANCZOS))
            return np.mean(tgt_arr) < 250

        # 预验证已有字符（随机打乱后取前 num_chars 个能渲染的）
        import random
        random.seed(42)
        shuffled_existing = list(train_chars)
        random.shuffle(shuffled_existing)
        existing = []
        for ch in shuffled_existing:
            if len(existing) >= num_chars:
                break
            if _can_render(ord(ch)):
                existing.append(ch)

        # 预验证新字符
        shuffled_new = list(all_cjk)
        random.shuffle(shuffled_new)
        new_chars = []
        for ch in shuffled_new:
            if len(new_chars) >= num_chars:
                break
            if _can_render(ord(ch)):
                new_chars.append(ch)

        # 构建 npz 数据
        ref_img = ref_renderer.render(ord('永'))
        ref_array = np.array(ref_img.resize((ref_size, ref_size), Image.Resampling.LANCZOS)).transpose(2, 0, 1)

        font_labels, char_labels, style_images, content_images, target_images, unicode_labels = [], [], [], [], [], []
        char_list = []

        for idx, ch in enumerate(existing + new_chars):
            codepoint = ord(ch)
            src_img = _render_source(codepoint)
            src_array = np.array(src_img.resize((resolution, resolution), Image.Resampling.LANCZOS)).transpose(2, 0, 1)
            tgt_img = target_renderer.render(codepoint)
            tgt_array = np.array(tgt_img.resize((resolution, resolution), Image.Resampling.LANCZOS)).transpose(2, 0, 1)

            font_labels.append(0)
            char_labels.append(idx)
            style_images.append(ref_array)
            content_images.append(src_array)
            target_images.append(tgt_array)
            unicode_labels.append(codepoint)
            char_list.append((ch, 'existing' if idx < len(existing) else 'new'))

        test_npz = os.path.join(output_dir, '_test_quick.npz')
        np.savez(test_npz,
                 font_labels=np.array(font_labels),
                 char_labels=np.array(char_labels),
                 style_images=np.array(style_images),
                 content_images=np.array(content_images),
                 target_images=np.array(target_images),
                 unicode_labels=np.array(unicode_labels),
                 num_original_samples=np.array(len(font_labels)))

        # 调用 generate_chars.py 生成图片
        gen_output = os.path.join(output_dir, '_test_quick_output')
        gen_folder = os.path.join(gen_output, 'generated')
        os.makedirs(gen_folder, exist_ok=True)

        script = os.path.join(ZI2ZI_DIR, "generate_chars.py")
        cmd = [
            ZI2ZI_PYTHON, script,
            "--checkpoint", checkpoint_path,
            "--test_npz", test_npz,
            "--output_dir", gen_output,
            "--batch_size", "64",
            "--pairwise", "target_gen",
        ]

        proc = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', cwd=ZI2ZI_DIR)
        if proc.returncode != 0:
            return {"success": False, "error": f"生成失败: {proc.stderr[:500]}"}

        # 收集结果图片
        compare_dir = None
        for sub in os.listdir(gen_output):
            sub_path = os.path.join(gen_output, sub)
            if os.path.isdir(sub_path) and 'compare' in os.listdir(sub_path) if os.path.isdir(sub_path) else False:
                compare_dir = os.path.join(sub_path, 'compare')
                gen_folder = os.path.join(sub_path, 'generated')
                break

        results = []
        for ch, ctype in char_list:
            codepoint = ord(ch)
            hex_str = f"{codepoint:04X}" if codepoint <= 0xFFFF else f"{codepoint:05X}"
            prefix = 'uni' if codepoint <= 0xFFFF else 'u'

            gen_path = None
            compare_path = None

            # 查找生成图片（可能有也可能没有汉字后缀）
            for f in os.listdir(gen_folder):
                if f.startswith(f'{prefix}{hex_str}') and f.endswith('.png'):
                    gen_path = os.path.join(gen_folder, f)
                    break

            if compare_dir:
                for f in os.listdir(compare_dir):
                    if f.startswith(f'{prefix}{hex_str}') and f.endswith('.png'):
                        compare_path = os.path.join(compare_dir, f)
                        break

            results.append({
                "char": ch,
                "codepoint": codepoint,
                "type": ctype,
                "gen_image": gen_path,
                "compare_image": compare_path,
            })

        return {
            "success": True,
            "results": results,
            "existing_count": len(existing),
            "new_count": len(new_chars),
        }

    def get_status(self):
        """获取训练状态"""
        elapsed = time.time() - self.start_time if self.start_time else 0
        return {
            "status": self.status,
            "epoch": self.current_epoch,
            "total_epochs": self.total_epochs,
            "loss": round(self.current_loss, 4),
            "lr": self.current_lr,
            "elapsed": round(elapsed, 1),
            "error": self.error_message,
            "log_path": self.log_path,
            "last_params": self.last_params,
        }

    def get_logs(self, offset=0, limit=100):
        """读取日志"""
        if not self.log_path or not os.path.exists(self.log_path):
            return {"lines": [], "total": 0}

        lines = []
        with open(self.log_path, 'r', encoding='utf-8', errors='replace') as f:
            all_lines = f.readlines()

        total = len(all_lines)
        selected = all_lines[offset:offset + limit]
        lines = [l.rstrip() for l in selected]

        return {"lines": lines, "total": total, "offset": offset}


# 全局单例
train_manager = TrainManager()
