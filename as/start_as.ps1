$env:AUTH_DB_HOST='127.0.0.1'
$env:AUTH_DB_PORT='3306'
$env:AUTH_DB_USER='root'
$env:AUTH_DB_PASSWORD='811019lin'
$env:AUTH_DB_NAME='SafetyWork'

$env:AS_RSA_PRIVATE_KEY_PATH='E:\git\SafetyWork\as\as_private_key.json'
$env:K_TGS_BASE64=(Get-Content 'E:\git\SafetyWork\as\k_tgs_base64.txt' -Raw).Trim()

$env:AS_HOST='0.0.0.0'
$env:AS_PORT='9000'
Write-Host "AS K_TGS_BASE64=[$env:K_TGS_BASE64]"
python .\as\as_server.py
