$env:AUTH_DB_HOST='172.27.143.193'
$env:AUTH_DB_PORT='3306'
$env:AUTH_DB_USER='game_user'
$env:AUTH_DB_PASSWORD='811019lin'
$env:AUTH_DB_NAME='safetywork'

$env:K_TGS_BASE64=(Get-Content 'F:\SafetyWork\as\k_tgs_base64.txt' -Raw).Trim()

# 这里填你生成的 K_GS_BASE64，TGS 和 GS 必须完全一样
$env:K_GS_BASE64='RYz5juaShC4='

$env:TGS_HOST='0.0.0.0'
$env:TGS_PORT='9001'
$env:AUTH_GS_SERVICE_NAME='game/ws@172.27.143.193:8765'
Write-Host "TGS K_TGS_BASE64=[$env:K_TGS_BASE64]"
py tgs_server.py

# .\start_tgs.ps1