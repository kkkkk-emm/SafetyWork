

$env:AUTH_DB_HOST='127.0.0.1'
$env:AUTH_DB_PORT='3306'
$env:AUTH_DB_USER='root'
$env:AUTH_DB_PASSWORD='811019lin'
$env:AUTH_DB_NAME='safetywork'

$env:K_TGS_BASE64=(Get-Content 'E:\github\SafetyWork\as\k_tgs_base64.txt' -Raw).Trim()

# 这里填你生成的 K_GS_BASE64，TGS 和 GS 必须完全一样
$env:K_GS_BASE64='RYz5juaShC4='

$env:TGS_HOST='0.0.0.0'
$env:TGS_PORT='9001'
$env:AUTH_GS_SERVICE_NAME='game/ws@127.0.0.1:8765'
Write-Host "TGS K_TGS_BASE64=[$env:K_TGS_BASE64]"
python .\tgs\tgs_server.py