$ErrorActionPreference = 'Stop'
$networkWebRoot = Split-Path -Parent $PSScriptRoot
$networkConfigPath = Join-Path $networkWebRoot '../local/web/runtime/network.json'
$networkConfig = Get-Content -LiteralPath $networkConfigPath -Raw | ConvertFrom-Json
if ($networkConfig.schemaVersion -ne 'web-network.v1') { throw 'Unsupported network configuration' }
$env:WEB_HOST = [string]$networkConfig.bindHost
$env:WEB_PORT = [string]$networkConfig.port
$env:WEB_ORIGINS = $networkConfig.origins -join ','
$networkNode = (Get-Command node -ErrorAction Stop).Source
& $networkNode (Join-Path $networkWebRoot 'src/server.mjs')
exit $LASTEXITCODE
