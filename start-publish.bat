@echo off
REM Start the stock-selection system and expose it via Cloudflare Tunnel.
cd /d D:\WorkBuddy

REM 1) Start local server (with access token). Change stock2026 to your own password.
start "StockServer" cmd /k "set SITE_TOKEN=stock2026&& node serve.js"

REM 2) Wait a moment, then start the public tunnel if cloudflared is ready.
timeout /t 2 >nul
if exist cloudflared.exe (
  start "PublicTunnel" cmd /k "cloudflared.exe tunnel --url http://localhost:8080 --no-autoupdate"
) else (
  echo cloudflared.exe not found. Run "cloudflared.exe tunnel --url http://localhost:8080" after it finishes downloading.
)
