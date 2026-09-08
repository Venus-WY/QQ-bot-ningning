@echo off
cd /d "%~dp0"

echo ==========================================
echo   一键启动: NapCat(QQ) + QQ群AI群友
echo ==========================================
echo.

echo [1/2] 启动 NapCat / QQ ...
start "NapCat-QQ" "napcat\launcher-custom.bat"

timeout /t 3 /nobreak >nul

echo [2/2] 启动 bot ...
start "QQ-AI-群友" "qq-bot\启动.bat"

echo.
echo 已打开两个窗口:
echo   [NapCat-QQ]    QQ 登录 / OneBot 连接 (未登录会弹二维码, 扫一次即可)
echo   [QQ-AI-群友]   bot 本体 (改文件会自动重启)
echo.
echo 关掉对应窗口 = 停对应程序。登录态正常时, 下次启动无需再扫码。
echo.
timeout /t 8
