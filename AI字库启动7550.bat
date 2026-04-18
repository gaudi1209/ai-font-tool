@echo off
chcp 65001 >nul
title AI字体生产工具
echo 正在启动 AI字体生产工具...
echo 访问地址: http://localhost:7550
echo 按 Ctrl+C 停止服务
echo.
python app.py
pause
