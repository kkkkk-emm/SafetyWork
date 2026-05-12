$env:AUTH_DB_HOST='127.0.0.1'
$env:AUTH_DB_PORT='3306'
$env:AUTH_DB_USER='root'
$env:AUTH_DB_PASSWORD='811019lin'
$env:AUTH_DB_NAME='SafetyWork'

# 必须和 TGS 里的 K_GS_BASE64 一样
$env:K_GS_BASE64='RYz5juaShC4='

$env:GS_HOST='0.0.0.0'
$env:GS_PORT='8765'
$env:AUTH_GS_SERVICE_NAME='game/ws@172.27.143.193:8765'

python .\server\ws_server.py