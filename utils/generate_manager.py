# -*- coding: utf-8 -*-
"""迭代生成管理器 - 管理zi2zi-JiT生成+OCR验证流程"""

import os
import sys
import subprocess
import threading
import time
import json
import re
import shutil
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config import ZI2ZI_DIR, ZI2ZI_PYTHON, OCR_PYTHON


class GenerateManager:
    def __init__(self):
        self.status = "idle"
        self.error_message = ""
        self.total_chars = 0
        self.success_chars = 0
        self.current_round = 0
        self.max_rounds = 20
        self.start_time = None
        self.round_log = []
        self._stop_flag = False
        self._thread = None
        self._current_process = None
        self._pid_file = os.path.join(tempfile.gettempdir(), 'gen_v6_subprocess.pid')
        self.output_dir = ''  # 当前输出目录

    def _save_pid(self, pid):
        try:
            with open(self._pid_file, 'w') as f:
                f.write(str(pid))
        except:
            pass

    def _kill_saved_pid(self):
        try:
            with open(self._pid_file, 'r') as f:
                pid = int(f.read().strip())
            os.kill(pid, 9)  # SIGKILL
            self.round_log.append(f"已终止子进程 PID={pid}")
        except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
            pass
        try:
            os.unlink(self._pid_file)
        except:
            pass

    def start_generate(self, params):
        """启动迭代生成"""
        if self.status == "generating":
            return {"success": False, "error": "生成正在进行中"}

        self._stop_flag = False
        self.status = "generating"
        self.error_message = ""
        self.success_chars = 0
        self.current_round = 0
        self.start_time = time.time()
        self.round_log = []
        self.output_dir = params.get('output_dir', '')

        self._thread = threading.Thread(target=self._run_generate, args=(params,), daemon=True)
        self._thread.start()
        return {"success": True, "message": "生成已启动"}

    def stop_generate(self):
        """停止生成，立即终止子进程"""
        self._stop_flag = True
        # 先尝试通过对象引用终止
        if self._current_process and self._current_process.poll() is None:
            self._current_process.kill()
        # 再通过PID文件兜底终止
        self._kill_saved_pid()
        return {"success": True, "message": "正在停止..."}

    def get_status(self):
        """获取状态"""
        elapsed = time.time() - self.start_time if self.start_time else 0
        return {
            "status": self.status,
            "total_chars": self.total_chars,
            "success_chars": self.success_chars,
            "pending_chars": self.total_chars - self.success_chars,
            "current_round": self.current_round,
            "max_rounds": self.max_rounds,
            "elapsed": round(elapsed, 1),
            "error": self.error_message,
            "progress": round(self.success_chars / self.total_chars * 100, 1) if self.total_chars > 0 else 0,
            "round_log": self.round_log[-10:],
            "output_dir": self.output_dir,
        }

    def _run_generate(self, params):
        """迭代生成主循环"""
        try:
            chars = params.get('chars', [])
            output_dir = params.get('output_dir', '')
            checkpoint = params.get('checkpoint', '')
            ref_font = params.get('ref_font', '')
            source_font = params.get('source_font', '')
            multiplier = params.get('multiplier', 5)
            max_rounds = params.get('max_rounds', 20)
            threshold = params.get('threshold', 0.5)
            cfg = params.get('cfg', 2.6)
            resolution = params.get('resolution', 256)
            ref_size = params.get('ref_size', 128)
            batch_size = params.get('batch_size', 64)

            self.total_chars = len(chars)
            self.max_rounds = max_rounds

            # 在 output_dir 下创建带时间戳的子目录
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            actual_output_dir = os.path.join(output_dir, f"gen_{timestamp}")
            os.makedirs(actual_output_dir, exist_ok=True)
            self.output_dir = actual_output_dir

            # 已成功的字符（扫描原始 output_dir 下所有子目录和文件）
            success_codes = set()
            for root, dirs, filenames in os.walk(output_dir):
                for f in filenames:
                    if f.startswith('uni') or f.startswith('u'):
                        try:
                            m = re.match(r'^(?:uni|u)([0-9A-Fa-f]+)', f)
                            if m:
                                success_codes.add(int(m.group(1), 16))
                        except:
                            pass

            # 只计本次任务中已有的成功数
            self.success_chars = sum(1 for c in chars if ord(c) in success_codes)

            pending = [c for c in chars if ord(c) not in success_codes]
            codepoint_to_char = {ord(c): c for c in chars}

            if not pending:
                self.status = "completed"
                return

            # 校验字体路径
            if not source_font or not os.path.isfile(source_font):
                self.status = "error"
                self.error_message = f"源字体路径无效：{source_font or '（未填写）'}，请在生成页面填写源字体路径"
                return
            if not ref_font or not os.path.isfile(ref_font):
                self.status = "error"
                self.error_message = f"学习字库路径无效：{ref_font or '（未填写）'}，请在生成页面填写学习字库TTF路径"
                return

            # 预检查：移除源字体无法渲染的字符
            sys.path.insert(0, ZI2ZI_DIR)
            from data_processing.font_utils import GlyphRenderer
            import numpy as np
            from PIL import Image
            from fontTools.ttLib import TTFont

            src_renderer = GlyphRenderer(source_font, resolution)
            # 扩展区字库：前端传入优先，否则默认宋体扩展B
            ext_font_path = params.get('ext_font', '') or r'C:\Windows\Fonts\simsunb.ttf'
            ext_renderer = GlyphRenderer(ext_font_path, resolution) if os.path.isfile(ext_font_path) else None

            # 用 cmap 精确检查字符是否在字体中
            try:
                src_tt = TTFont(source_font, fontNumber=0) if source_font.endswith('.ttc') else TTFont(source_font)
                src_cmap = src_tt.getBestCmap() or {}
                src_tt.close()
            except Exception:
                src_cmap = {}

            ext_cmap = {}
            if ext_renderer and os.path.exists(ext_font_path):
                try:
                    ext_tt = TTFont(ext_font_path)
                    ext_cmap = ext_tt.getBestCmap() or {}
                    ext_tt.close()
                except Exception:
                    pass

            def _render_source(codepoint):
                """渲染源字符，source font 不包含时 fallback 到扩展区字体"""
                renderer = src_renderer if codepoint in src_cmap else ext_renderer
                if renderer is None:
                    return None
                img = renderer.render(codepoint)
                if img is None:
                    return None
                arr = np.array(img.resize((resolution, resolution), Image.Resampling.LANCZOS))
                if np.mean(arr) > 250:
                    return None
                return img

            unrenderable = []
            for c in list(pending):
                cp = ord(c)
                img = _render_source(cp)
                if img is None:
                    unrenderable.append(c)
                    pending.remove(c)
                else:
                    arr = np.array(img.resize((resolution, resolution), Image.Resampling.LANCZOS))
                    if np.mean(arr) > 250:
                        unrenderable.append(c)
                        pending.remove(c)
            if unrenderable:
                self.round_log.append(
                    f"⚠ 源字体不支持 {len(unrenderable)} 个字符（已跳过）: {''.join(unrenderable[:30])}"
                )
            if not pending:
                self.round_log.append("所有字符源字体均无法渲染，任务结束")
                self.status = "completed"
                return

            for round_num in range(1, max_rounds + 1):
                if self._stop_flag:
                    self.status = "stopped"
                    return
                if not pending:
                    break

                self.current_round = round_num
                round_start = time.time()

                # 创建npz
                expanded = pending * multiplier
                work_dir = tempfile.mkdtemp(prefix="gen_v6_")
                temp_npz = os.path.join(work_dir, "pending.npz")

                self.round_log.append(f"Round {round_num}: {len(pending)} 字待处理")

                try:
                    num_samples = self._create_npz(expanded, temp_npz, ref_font, source_font, resolution, ref_size, ext_font_path)
                    if num_samples == 0:
                        shutil.rmtree(work_dir, ignore_errors=True)
                        continue

                    # 生成图片
                    gen_dir = os.path.join(work_dir, "generated")
                    self._run_generate_cmd(checkpoint, temp_npz, gen_dir, num_samples, cfg, batch_size)

                    png_files = self._find_png_files(gen_dir)
                    if not png_files:
                        shutil.rmtree(work_dir, ignore_errors=True)
                        continue

                    # OCR验证
                    ocr_results = self._ocr_verify(png_files)

                    # 筛选最佳
                    pat = re.compile(r'^(?:uni|u)([0-9A-Fa-f]+)')
                    char_best = {}

                    for path in png_files:
                        fname = os.path.basename(path)
                        m = pat.match(fname)
                        if not m:
                            continue
                        code = int(m.group(1), 16)
                        if code not in codepoint_to_char:
                            continue
                        conf = ocr_results.get(path, 0)
                        if conf >= threshold:
                            if code not in char_best or conf > char_best[code][1]:
                                char_best[code] = (path, conf)

                    # 复制成功的（FontLab命名：默认带汉字后缀）
                    round_success = 0
                    for code, (path, conf) in char_best.items():
                        if code not in success_codes:
                            char = chr(code)
                            if code > 0xFFFF:
                                fname = f"u{code:05X}_{char}.png"
                            else:
                                fname = f"uni{code:04X}_{char}.png"
                            shutil.copy(path, os.path.join(actual_output_dir, fname))
                            success_codes.add(code)
                            round_success += 1

                    self.success_chars = sum(1 for c in chars if ord(c) in success_codes)
                    elapsed = time.time() - round_start
                    self.round_log.append(
                        f"Round {round_num}: 成功 {round_success}, 累计 {self.success_chars}/{self.total_chars} ({elapsed:.0f}s)"
                    )

                    pending = [c for c in chars if ord(c) not in success_codes]

                finally:
                    shutil.rmtree(work_dir, ignore_errors=True)

                if round_success == 0 and round_num >= 3:
                    self.round_log.append(f"连续无新增，剩余 {len(pending)} 字")

            self.status = "completed"

        except Exception as e:
            self.status = "error"
            self.error_message = str(e)

    def _create_npz(self, chars, output_path, ref_font, source_font, resolution, ref_size, ext_font=''):
        """创建npz，源字体无法渲染的字符自动 fallback 到扩展区字体"""
        import numpy as np
        from PIL import Image
        from fontTools.ttLib import TTFont

        sys.path.insert(0, ZI2ZI_DIR)
        from data_processing.font_utils import GlyphRenderer

        source_renderer = GlyphRenderer(source_font, resolution)
        ref_renderer = GlyphRenderer(ref_font, ref_size)

        # 扩展区字库：使用传入的扩展字库，否则默认宋体扩展B
        ext_font_path = ext_font or r'C:\Windows\Fonts\simsunb.ttf'
        ext_renderer = GlyphRenderer(ext_font_path, resolution) if os.path.isfile(ext_font_path) else None

        # cmap 检查
        try:
            src_tt = TTFont(source_font, fontNumber=0) if source_font.endswith('.ttc') else TTFont(source_font)
            src_cmap = src_tt.getBestCmap() or {}
            src_tt.close()
        except Exception:
            src_cmap = {}
        ext_cmap = {}
        if ext_renderer:
            try:
                ext_tt = TTFont(ext_font_path)
                ext_cmap = ext_tt.getBestCmap() or {}
                ext_tt.close()
            except Exception:
                pass

        def _render_source(codepoint):
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

        ref_img = ref_renderer.render(ord('永'))
        ref_array = np.array(ref_img.resize((ref_size, ref_size), Image.Resampling.LANCZOS))
        ref_array = ref_array.transpose(2, 0, 1)

        font_labels, char_labels, style_images, content_images, unicode_labels = [], [], [], [], []
        skipped = []

        for char in chars:
            codepoint = ord(char)
            src_img = _render_source(codepoint)
            if src_img is None:
                skipped.append(char)
                continue
            src_array = np.array(src_img.resize((resolution, resolution), Image.Resampling.LANCZOS))
            src_array = src_array.transpose(2, 0, 1)

            font_labels.append(0)
            char_labels.append(0)
            style_images.append(ref_array.copy())
            content_images.append(src_array)
            unicode_labels.append(codepoint)

        if skipped:
            unique_skipped = sorted(set(skipped))
            self.round_log.append(f"跳过 {len(unique_skipped)} 个源字体无法渲染的字符: {''.join(unique_skipped[:20])}")

        if not font_labels:
            return 0

        np.savez(output_path,
                 font_labels=np.array(font_labels),
                 char_labels=np.array(char_labels),
                 style_images=np.array(style_images),
                 content_images=np.array(content_images),
                 unicode_labels=np.array(unicode_labels),
                 num_original_samples=np.array(len(font_labels)))
        return len(font_labels)

    def _run_generate_cmd(self, checkpoint, npz_path, output_dir, num_images, cfg, batch_size):
        """调用generate_chars.py，支持中途终止"""
        cmd = [
            ZI2ZI_PYTHON,
            os.path.join(ZI2ZI_DIR, "generate_chars.py"),
            "--checkpoint", checkpoint,
            "--test_npz", npz_path,
            "--output_dir", output_dir,
            "--sampling_method", "heun",
            "--num_sampling_steps", "50",
            "--cfg", str(cfg),
            "--batch_size", str(batch_size),
            "--num_images", str(num_images)
        ]
        try:
            self._current_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=ZI2ZI_DIR)
            self._save_pid(self._current_process.pid)
            self._current_process.wait(timeout=1800)
            return self._current_process.returncode == 0
        except subprocess.TimeoutExpired:
            self._current_process.kill()
            return False
        finally:
            self._current_process = None

    def _find_png_files(self, directory):
        """递归查找png"""
        files = []
        for root, dirs, filenames in os.walk(directory):
            for f in filenames:
                if f.endswith('.png'):
                    files.append(os.path.join(root, f))
        return files

    def _ocr_verify(self, img_paths):
        """OCR置信度验证"""
        if not img_paths:
            return {}

        # 分批处理，每批100个
        batch_size = 100
        all_results = {}

        for i in range(0, len(img_paths), batch_size):
            batch = img_paths[i:i + batch_size]
            data_json = json.dumps({"img_paths": batch}, ensure_ascii=False)

            script = f'''
import os
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'
from paddleocr import PaddleOCR
from PIL import Image
import numpy as np
import json

data = json.loads(r"""{data_json}""")
img_paths = data["img_paths"]

ocr = PaddleOCR(lang='ch', use_gpu=False, show_log=False)

results = {{}}
for img_path in img_paths:
    try:
        img = np.array(Image.open(img_path))
        result = ocr.ocr(img, cls=False)
        if result and result[0]:
            conf = result[0][0][1][1]
            results[img_path] = conf
        else:
            results[img_path] = 0.0
    except Exception as e:
        results[img_path] = 0.0

print("===RESULTS===")
print(json.dumps(results))
'''

            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                f.write(script)
                temp_script = f.name

            try:
                result = subprocess.run([OCR_PYTHON, temp_script], capture_output=True, text=True, timeout=600)
                if "===RESULTS===" in result.stdout:
                    json_str = result.stdout.split("===RESULTS===")[1].strip()
                    all_results.update(json.loads(json_str))
            except Exception as e:
                self.round_log.append(f"OCR error: {str(e)[:100]}")
            finally:
                os.unlink(temp_script)

        return all_results


# 全局单例
generate_manager = GenerateManager()
