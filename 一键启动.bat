@echo off
cd /d "%~dp0"

REM ============ 查找 NapCat 目录（按优先级） ============
REM 1) 项目内 napcat\  2) 上级目录 napcat-shell\  3) 上级目录 napcat\
set "NAPCAT_DIR="
if exist "%~dp0napcat\launcher-user.bat" set "NAPCAT_DIR=%~dp0napcat"
if not defined NAPCAT_DIR if exist "%~dp0..\napcat-shell\launcher-user.bat" set "NAPCAT_DIR=%~dp0..\napcat-shell"
if not defined NAPCAT_DIR if exist "%~dp0..\napcat\launcher-user.bat" set "NAPCAT_DIR=%~dp0..\napcat"

echo ==========================================
echo   一键启动: NapCat(QQ) + QQ群AI群友
echo ==========================================
echo.

if not defined NAPCAT_DIR (
    echo [错误] 未找到 NapCat 目录。
    echo 请把 NapCat.Shell 解压到本目录的 napcat\ 子目录，
    echo 或把本脚本和 NapCat 放在同一级目录（napcat-shell 目录）。
    echo 也可以手动编辑本脚本开头的 NAPCAT_DIR 变量。
    echo.
    pause
    exit /b 1
)

echo [1/2] 启动 NapCat / QQ ...
start "NapCat-QQ" /D "%NAPCAT_DIR%" launcher-user.bat

timeout /t 3 /nobreak >nul

echo [2/2] 启动 bot ...
start "QQ-AI-群友" "%~dp0qq-bot\启动.bat"

echo.
echo 已打开两个窗口:
echo   [NapCat-QQ]    QQ 登录 / OneBot 连接 (未登录会弹二维码, 扫一次即可)
echo   [QQ-AI-群友]   bot 本体 (改文件会自动重启)
echo.
echo 关掉对应窗口 = 停对应程序。登录态正常时, 下次启动无需再扫码。
echo.
timeout /t 8
