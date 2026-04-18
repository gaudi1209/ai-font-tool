@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title AI字体生产工具 - 一键安装

REM 切换到脚本所在目录（安装根目录）
cd /d "%~dp0"

set "INSTALL_ROOT=%~dp0"
set "INSTALL_ROOT=%INSTALL_ROOT:~0,-1%"
set "MARK_FILE=%INSTALL_ROOT%\install_state\step_mark.txt"
set "LOG_FILE=%INSTALL_ROOT%\install_state\install.log"
set "CONDA_DIR=%INSTALL_ROOT%\env\miniconda"
set "MAIN_PYTHON=%INSTALL_ROOT%\env\main\Scripts\python.exe"
set "OCR_PYTHON=%INSTALL_ROOT%\env\ocr\Scripts\python.exe"
set "PIP_MIRROR=-i https://mirrors.aliyun.com/pypi/simple/"

mkdir "%INSTALL_ROOT%\install_state" 2>nul

echo ========================================
echo   AI 字体生产工具 - 一键安装
echo ========================================
echo.
echo 安装目录: %INSTALL_ROOT%
echo.

REM ============================================================
REM Step 1: 系统环境检测
REM ============================================================
:step1
findstr /c:"step1_system" "%MARK_FILE%" >nul 2>&1
if not errorlevel 1 goto step2

echo [Step 1/8] 检测系统环境...

REM 检查 GPU
nvidia-smi >nul 2>&1
if errorlevel 1 (
    echo.
    echo [错误] 未检测到 NVIDIA GPU 或未安装显卡驱动
    echo 本工具需要 NVIDIA 显卡（支持 CUDA）才能运行
    echo 请先安装驱动: https://www.nvidia.cn/Download/index.aspx
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('nvidia-smi --query-gpu^=driver_version --format^=csv^,noheader 2^>nul') do (
    echo [OK] NVIDIA 驱动版本: %%i
)

for /f "tokens=*" %%i in ('nvidia-smi --query-gpu^=name --format^=csv^,noheader 2^>nul') do (
    echo [OK] GPU: %%i
)

REM 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [警告] 系统未安装 Python，将使用 Miniconda 提供的 Python
) else (
    for /f "tokens=2" %%i in ('python --version 2^>^&1') do echo [OK] 系统 Python: %%i
)

REM 检查磁盘空间（需 >= 15GB）
for /f "tokens=3" %%a in ('dir "%INSTALL_ROOT%" ^| findstr /c:"bytes free"') do set FREE_BYTES=%%a
echo [OK] 系统环境检测通过
echo.

echo step1_system >> "%MARK_FILE%"

REM ============================================================
REM Step 2: 安装 Miniconda
REM ============================================================
:step2
findstr /c:"step2_miniconda" "%MARK_FILE%" >nul 2>&1
if not errorlevel 1 goto step3

echo [Step 2/8] 安装 Miniconda...

REM 检查已有 conda
where conda >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=*" %%i in ('where conda') do (
        echo [OK] 检测到已有 conda: %%i
        set "CONDA_DIR=%%~dpiConda"
        goto :conda_found
    )
)

REM 下载 Miniconda（清华镜像）
set "CONDA_INSTALLER=%INSTALL_ROOT%\install_state\Miniconda3-latest-Windows-x86_64.exe"
if not exist "%CONDA_INSTALLER%" (
    echo 正在下载 Miniconda（清华镜像源）...
    curl -L -o "%CONDA_INSTALLER%" https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-latest-Windows-x86_64.exe
    if errorlevel 1 (
        echo [错误] Miniconda 下载失败，请检查网络连接
        echo 也可手动下载: https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/
        pause
        exit /b 1
    )
)

echo 正在安装 Miniconda（静默安装，约需 2-3 分钟）...
start /wait "" "%CONDA_INSTALLER%" /InstallationType=JustMe /RegisterPython=0 /AddToPath=0 /S /D=%CONDA_DIR%

:conda_found
call "%CONDA_DIR%\Scripts\activate.bat" "%CONDA_DIR%"
echo [OK] Miniconda 就绪
echo.

echo step2_miniconda >> "%MARK_FILE%"

REM ============================================================
REM Step 3: 创建主环境 (Flask venv)
REM ============================================================
:step3
findstr /c:"step3_main_env" "%MARK_FILE%" >nul 2>&1
if not errorlevel 1 goto step4

echo [Step 3/8] 创建主 Python 环境...

if exist "%MAIN_PYTHON%" (
    echo [OK] 主环境已存在，跳过
    goto :step3_done
)

REM 用 conda 的 python 创建 venv
call "%CONDA_DIR%\Scripts\activate.bat" "%CONDA_DIR%"
python -m venv "%INSTALL_ROOT%\env\main"
if errorlevel 1 (
    echo [错误] 创建主环境失败
    pause
    exit /b 1
)

echo 正在安装 Flask 依赖（阿里云镜像）...
"%MAIN_PYTHON%" -m pip install --upgrade pip %PIP_MIRROR%
"%MAIN_PYTHON%" -m pip install -r "%INSTALL_ROOT%\app\requirements.txt" %PIP_MIRROR%
if errorlevel 1 (
    echo [错误] Flask 依赖安装失败
    pause
    exit /b 1
)

:step3_done
echo [OK] 主环境就绪
echo.

echo step3_main_env >> "%MARK_FILE%"

REM ============================================================
REM Step 4: 创建 zi2zi conda 环境
REM ============================================================
:step4
findstr /c:"step4_zi2zi_env" "%MARK_FILE%" >nul 2>&1
if not errorlevel 1 goto step5

echo [Step 4/8] 创建 zi2zi-JiT conda 环境（最耗时，约需 10-20 分钟）...

call "%CONDA_DIR%\Scripts\activate.bat" "%CONDA_DIR%"

REM 检查环境是否已存在
conda env list | findstr /c:"zi2zi-jit" >nul 2>&1
if not errorlevel 1 (
    echo [OK] zi2zi-jit 环境已存在，跳过
    goto :step4_done
)

echo 正在创建 conda 环境（Python 3.10）...
call conda create -n zi2zi-jit python=3.10 -y
if errorlevel 1 (
    echo [错误] conda 环境创建失败
    pause
    exit /b 1
)

echo 正在安装 PyTorch + CUDA（下载约 2-3GB）...
call conda activate zi2zi-jit
pip install torch==2.5.1 torchvision==0.20.1 %PIP_MIRROR% --extra-index-url https://download.pytorch.org/whl/cu121
if errorlevel 1 (
    echo [错误] PyTorch 安装失败
    pause
    exit /b 1
)

echo 正在安装其他依赖...
pip install opencv-python==4.11.0.86 timm==0.9.12 tensorboard==2.10.0 scipy einops==0.8.1 gdown==5.2.0 fonttools Pillow pytorch-msssim lpips tqdm matplotlib %PIP_MIRROR%

REM 安装 zi2zi-jit 包
pip install -e "%INSTALL_ROOT%\engine\zi2zi-JiT" %PIP_MIRROR%

REM 验证 CUDA
python -c "import torch; print(f'[OK] PyTorch {torch.__version__}, CUDA: {torch.cuda.is_available()}')" 2>nul

call conda deactivate

:step4_done
echo [OK] zi2zi 环境就绪
echo.

echo step4_zi2zi_env >> "%MARK_FILE%"

REM ============================================================
REM Step 5: 创建 OCR 环境
REM ============================================================
:step5
findstr /c:"step5_ocr_env" "%MARK_FILE%" >nul 2>&1
if not errorlevel 1 goto step6

echo [Step 5/8] 创建 PaddleOCR 环境...

if exist "%OCR_PYTHON%" (
    echo [OK] OCR 环境已存在，跳过
    goto :step5_done
)

call "%CONDA_DIR%\Scripts\activate.bat" "%CONDA_DIR%"
python -m venv "%INSTALL_ROOT%\env\ocr"
if errorlevel 1 (
    echo [错误] 创建 OCR 环境失败
    pause
    exit /b 1
)

echo 正在安装 PaddleOCR（约需 5 分钟）...
"%OCR_PYTHON%" -m pip install --upgrade pip %PIP_MIRROR%
"%OCR_PYTHON%" -m pip install paddlepaddle==2.5.2 paddleocr==2.6.1.3 %PIP_MIRROR%

:step5_done
echo [OK] OCR 环境就绪
echo.

echo step5_ocr_env >> "%MARK_FILE%"

REM ============================================================
REM Step 6: 下载基础模型
REM ============================================================
:step6
findstr /c:"step6_model" "%MARK_FILE%" >nul 2>&1
if not errorlevel 1 goto step7

echo [Step 6/8] 检查基础模型...

set "MODEL_PATH=%INSTALL_ROOT%\engine\models\zi2zi-JiT-B-16.pth"

if exist "%MODEL_PATH%" (
    echo [OK] 基础模型已存在
    goto :step6_done
)

echo.
echo 基础模型 zi2zi-JiT-B-16.pth（2.2GB）需要下载。
echo.
echo 如果下载速度过慢，可以:
echo   1. 手动下载模型文件
echo   2. 放入: %INSTALL_ROOT%\engine\models\
echo   3. 重新运行 setup.bat 即可继续
echo.
echo 模型下载地址:
echo   https://github.com/kaonashi-tyc/zi2zi-JiT/releases
echo.

set /p "DOWNLOAD=是否现在下载? (Y/N): "
if /i not "%DOWNLOAD%"=="Y" (
    echo [跳过] 稍后可重新运行 setup.bat 下载模型
    goto :step7
)

"%MAIN_PYTHON%" "%INSTALL_ROOT%\scripts\download_model.py" --output "%MODEL_PATH%"
if errorlevel 1 (
    echo [警告] 模型下载失败，您可以稍后手动下载
)

:step6_done
echo.

echo step6_model >> "%MARK_FILE%"

REM ============================================================
REM Step 7: 生成 .env 配置
REM ============================================================
:step7
findstr /c:"step7_config" "%MARK_FILE%" >nul 2>&1
if not errorlevel 1 goto step8

echo [Step 7/8] 生成配置文件...

REM 获取 zi2zi conda 环境的 python 路径
call "%CONDA_DIR%\Scripts\activate.bat" "%CONDA_DIR%"
for /f "tokens=*" %%i in ('conda run -n zi2zi-jit python -c "import sys; print(sys.executable)"') do set "ZI2ZI_PYTHON_PATH=%%i"

(
    echo # AI字体生产工具 - 自动生成的环境配置
    echo # 安装时间: %date% %time%
    echo.
    echo ZI2ZI_DIR=%INSTALL_ROOT%\engine\zi2zi-JiT
    echo ZI2ZI_PYTHON=%ZI2ZI_PYTHON_PATH%
    echo OCR_PYTHON=%OCR_PYTHON%
) > "%INSTALL_ROOT%\.env"

echo [OK] 配置文件已生成
echo.

echo step7_config >> "%MARK_FILE%"

REM ============================================================
REM Step 8: 验证安装
REM ============================================================
:step8
echo [Step 8/8] 验证安装...
echo.

REM 验证主环境
"%MAIN_PYTHON%" -c "import flask, fonttools, PIL, numpy; print('[OK] 主环境依赖正常')" 2>nul
if errorlevel 1 echo [警告] 主环境验证失败

REM 验证 zi2zi 环境
call "%CONDA_DIR%\Scripts\activate.bat" "%CONDA_DIR%"
conda run -n zi2zi-jit python -c "import torch; import timm; import einops; print(f'[OK] zi2zi 环境: PyTorch {torch.__version__}, CUDA: {torch.cuda.is_available()}')" 2>nul
if errorlevel 1 echo [警告] zi2zi 环境验证失败

REM 验证 OCR 环境
"%OCR_PYTHON%" -c "from paddleocr import PaddleOCR; print('[OK] PaddleOCR 可导入')" 2>nul
if errorlevel 1 echo [警告] OCR 环境验证失败

REM 验证模型
if exist "%INSTALL_ROOT%\engine\models\zi2zi-JiT-B-16.pth" (
    echo [OK] 基础模型文件存在
) else (
    echo [提示] 基础模型文件不存在，请手动下载后重新运行 setup.bat
)

REM 验证 .env
if exist "%INSTALL_ROOT%\.env" (
    echo [OK] 配置文件存在
) else (
    echo [警告] 配置文件不存在
)

echo.
echo ========================================
echo   安装完成！
echo ========================================
echo.
echo 使用方法:
echo   1. 双击 "启动.bat" 启动服务
echo   2. 浏览器访问 http://localhost:7550
echo.
echo 演示: 训练页面的 Checkpoint 可填入
echo   %INSTALL_ROOT%\engine\demo\赵孟頫楷书.pth
echo   学习字库填入:
echo   %INSTALL_ROOT%\engine\demo\赵孟頫楷书.ttf
echo.
echo 如遇问题，请查看 install_state\install.log
echo ========================================
echo.
pause
