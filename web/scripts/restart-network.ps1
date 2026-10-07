[CmdletBinding(SupportsShouldProcess)]
param([int]$ExpectedPid = 73980)

$ErrorActionPreference = 'Stop'
$networkWebRoot = Split-Path -Parent $PSScriptRoot
$networkProjectRoot = Split-Path -Parent $networkWebRoot
$networkRuntimeRoot = Join-Path $networkProjectRoot 'local/web/runtime'
$networkConfigPath = Join-Path $networkRuntimeRoot 'network.json'
$networkConfig = Get-Content -LiteralPath $networkConfigPath -Raw | ConvertFrom-Json
$networkNode = (Get-Command node -ErrorAction Stop).Source
$networkServerPath = Join-Path $networkWebRoot 'src/server.mjs'

# Validate the saved configuration before stopping anything.
$env:WEB_HOST = [string]$networkConfig.bindHost
$env:WEB_PORT = [string]$networkConfig.port
$env:WEB_ORIGINS = $networkConfig.origins -join ','
if ($networkConfig.schemaVersion -ne 'web-network.v1' -or $networkConfig.port -ne 3091) {
    throw 'Unexpected network configuration; nothing was stopped.'
}
$networkModuleUrl = ([Uri](Join-Path $networkWebRoot 'src/network.mjs')).AbsoluteUri
& $networkNode --input-type=module -e "import {readNetworkConfig} from '$networkModuleUrl'; readNetworkConfig();"
if ($LASTEXITCODE -ne 0) { throw 'Invalid configuration; nothing was stopped.' }

$networkRecordedPid = [int](Get-Content -LiteralPath (Join-Path $networkRuntimeRoot 'server.pid') -Raw)
$networkListener = @(Get-NetTCPConnection -State Listen -LocalPort 3091)
$networkProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $ExpectedPid"
if ($networkRecordedPid -ne $ExpectedPid -or $networkListener.Count -ne 1 `
    -or $networkListener[0].OwningProcess -ne $ExpectedPid -or -not $networkProcess `
    -or $networkProcess.ExecutablePath -ne $networkNode `
    -or $networkProcess.CommandLine.Trim() -ne ('"' + $networkNode + '" src/server.mjs')) {
    throw 'The website process changed; nothing was stopped. Check the current PID.'
}
if (-not $PSCmdlet.ShouldProcess("Website PID $ExpectedPid on TCP3091", 'Restart with saved network.json')) { return }

Stop-Process -Id $ExpectedPid -ErrorAction Stop
$networkStopping = Get-Process -Id $ExpectedPid -ErrorAction SilentlyContinue
if ($networkStopping) { $networkStopping | Wait-Process -Timeout 10 -ErrorAction Stop }
Remove-Item Env:WEB_TRACE_NETWORK -ErrorAction SilentlyContinue
$networkStamp = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss')
$networkStdout = Join-Path $networkRuntimeRoot "network-$networkStamp.stdout.log"
$networkStderr = Join-Path $networkRuntimeRoot "network-$networkStamp.stderr.log"
$networkStarted = Start-Process -FilePath $networkNode -ArgumentList 'src/server.mjs' `
    -WorkingDirectory $networkWebRoot -WindowStyle Hidden `
    -RedirectStandardOutput $networkStdout -RedirectStandardError $networkStderr -PassThru
$networkStarted.Id | Set-Content -LiteralPath (Join-Path $networkRuntimeRoot 'server.pid')

$networkReady = $false
for ($networkAttempt = 0; $networkAttempt -lt 20; $networkAttempt++) {
    Start-Sleep -Milliseconds 250
    $networkStarted.Refresh()
    if ($networkStarted.HasExited) { throw "Website exited. Inspect $networkStderr" }
    try {
        $networkHealth = Invoke-WebRequest -Uri 'http://127.0.0.1:3091/health' -UseBasicParsing -TimeoutSec 2
        if ($networkHealth.StatusCode -eq 200) { $networkReady = $true; break }
    } catch {
        # Readiness polling is bounded; the last failure is rethrown, never reported as success.
        if ($networkAttempt -eq 19) { throw }
    }
}
if (-not $networkReady) { throw "Website did not become ready. Inspect $networkStderr" }
[pscustomobject]@{ pid=$networkStarted.Id; bindHost=$networkConfig.bindHost; port=$networkConfig.port;
    origins=$networkConfig.origins; replacedPid=$ExpectedPid; traceEnabled=$false;
    startedAt=[DateTime]::UtcNow.ToString('o'); stdout=$networkStdout; stderr=$networkStderr } |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $networkProjectRoot 'local/web/network/exposure-01/runtime.json') -Encoding utf8
Write-Output "Website ready. PID: $($networkStarted.Id)"
$networkConfig.origins | ForEach-Object { Write-Output $_ }
