@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title AI字体生产工具

REM 切换到脚本所在目录
cd /d "%~dp0"

REM 检查是否已安装
if not exist ".env" (
    echo.
    echo [错误] 未检测到安装配置
    echo 请先双击 setup.bat 完成安装
    echo.
    pause
    exit /b 1
)

set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

echo ========================================
echo   AI 字体生产工具
echo ========================================
echo.
echo 正在启动 Web 服务...
echo.
echo   访问地址: http://localhost:7550
echo   按 Ctrl+C 停止服务
echo ========================================
echo.

REM 激活主环境
if exist "env\main\Scripts\activate.bat" (
    call "env\main\Scripts\activate.bat"
) else (
    echo [警告] 主环境不存在，尝试使用系统 Python
)

cd app
python app.py

pause
