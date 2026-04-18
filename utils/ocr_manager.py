# -*- coding: utf-8 -*-
"""OCR管理器 - 通过subprocess调用PaddleOCR"""

import os
import sys
import subprocess
import threading
import time
import json
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config import OCR_PYTHON


class OCRManager:
    def __init__(self):
        self.status = "idle"
        self.error_message = ""
        self.total_files = 0
        self.processed_files = 0
        self.results = []
        self.start_time = None
        self._stop_flag = False
        self._debug_log = []

    def start_ocr(self, params):
        """启动OCR识别"""
        if self.status == "running":
            return {"success": False, "error": "OCR正在运行"}

        self._stop_flag = False
        self.status = "running"
        self.error_message = ""
        self.processed_files = 0
        self.results = []
        self.start_time = time.time()
        self._debug_log = [f"启动: input_dir={params.get('input_dir')}, model={params.get('ocr_model')}, python={params.get('ocr_python')}"]

        thread = threading.Thread(target=self._run_ocr, args=(params,), daemon=True)
        thread.start()
        return {"success": True, "message": "OCR已启动"}

    def stop_ocr(self):
        """停止OCR"""
        self._stop_flag = True
        return {"success": True}

    def get_status(self):
        """获取状态"""
        elapsed = time.time() - self.start_time if self.start_time else 0
        progress = (self.processed_files / self.total_files * 100) if self.total_files > 0 else 0
        return {
            "status": self.status,
            "total_files": self.total_files,
            "processed_files": self.processed_files,
            "progress": round(progress, 1),
            "elapsed": round(elapsed, 1),
            "error": self.error_message,
            "results_count": len(self.results),
            "debug": self._debug_log[-5:],
        }

    def get_results(self, offset=0, limit=100):
        """获取识别结果，自动移除已删除的文件"""
        # 过滤掉不存在的文件
        before = len(self.results)
        self.results = [r for r in self.results if os.path.isfile(r.get('path', ''))]
        if len(self.results) != before:
            self.processed_files = len(self.results)
            self.total_files = max(self.total_files, self.processed_files)

        return {
            "results": self.results[offset:offset + limit],
            "total": len(self.results),
        }

    def _run_ocr(self, params):
        """OCR主循环"""
        try:
            input_dir = params.get('input_dir', '')
            file_filter = params.get('file_filter', '*.png')
            batch_size = params.get('batch_size', 50)
            ocr_model = params.get('ocr_model', 'ch')
            ocr_python = params.get('ocr_python', OCR_PYTHON)

            if not input_dir or not os.path.isdir(input_dir):
                self.status = "error"
                self.error_message = f"目录不存在: {input_dir}"
                return

            # 收集文件
            import glob
            pattern = os.path.join(input_dir, '**', file_filter)
            files = sorted(glob.glob(pattern, recursive=True))
            self.total_files = len(files)
            self._debug_log.append(f"找到 {len(files)} 个文件 (pattern={pattern})")

            if not files:
                self._debug_log.append("无文件，完成")
                self.status = "completed"
                return

            # 分批OCR
            for i in range(0, len(files), batch_size):
                if self._stop_flag:
                    self.status = "stopped"
                    return

                batch = files[i:i + batch_size]
                batch_results = self._ocr_batch(batch, ocr_model, ocr_python)
                self.results.extend(batch_results)
                self.processed_files = min(i + batch_size, len(files))

            self.status = "completed"

        except Exception as e:
            self.status = "error"
            self.error_message = str(e)

    def _ocr_batch(self, img_paths, ocr_model='ch', ocr_python=None):
        """批量OCR"""
        if ocr_python is None:
            ocr_python = OCR_PYTHON

        # 通过临时JSON文件传递路径，避免转义问题
        data_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8')
        json.dump({"img_paths": img_paths}, data_file, ensure_ascii=False)
        data_file.close()
        data_path = data_file.name

        # 根据模型类型生成不同的初始化代码
        # PaddleOCR 2.x: handwriting/ch_server 都用 lang='ch'（PP-OCRv4）
        # lang 参数只支持: ch, en, korean, japan, chinese_cht 等
        lang_map = {
            'handwriting': 'ch',
            'ch_server': 'ch',
        }
        actual_lang = lang_map.get(ocr_model, ocr_model)
        ocr_init = f"ocr = PaddleOCR(lang='{actual_lang}', use_gpu=False, show_log=False)"

        script = f'''
import os, sys, json
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'

data_path = sys.argv[1]
with open(data_path, 'r', encoding='utf-8') as f:
    data = json.load(f)
img_paths = data["img_paths"]

from paddleocr import PaddleOCR
from PIL import Image
import numpy as np

{ocr_init}

results = []
for img_path in img_paths:
    try:
        img = np.array(Image.open(img_path))
        result = ocr.ocr(img, cls=False)
        if result and result[0]:
            text = result[0][0][1][0]
            conf = result[0][0][1][1]
            results.append({{"path": img_path, "text": text, "confidence": round(conf, 4)}})
        else:
            results.append({{"path": img_path, "text": "", "confidence": 0}})
    except Exception as e:
        results.append({{"path": img_path, "text": "", "confidence": 0, "error": str(e)}})

print("===RESULTS===")
print(json.dumps(results, ensure_ascii=False))
'''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(script)
            temp_script = f.name

        try:
            result = subprocess.run([ocr_python, temp_script, data_path],
                                    capture_output=True, text=True, timeout=600)
            if "===RESULTS===" in result.stdout:
                json_str = result.stdout.split("===RESULTS===")[1].strip()
                parsed = json.loads(json_str)
                self._debug_log.append(f"批次成功: {len(parsed)} 个结果")
                return parsed
            else:
                err = result.stderr[:500] if result.stderr else (result.stdout[:500] if result.stdout else '无输出')
                self.error_message = f"OCR脚本错误: {err}"
                self._debug_log.append(f"批次失败: {err[:200]}")
        except Exception as e:
            self.error_message = str(e)[:300]
            self._debug_log.append(f"异常: {str(e)[:200]}")
        finally:
            os.unlink(temp_script)
            os.unlink(data_path)

        return []


# 全局单例
ocr_manager = OCRManager()
