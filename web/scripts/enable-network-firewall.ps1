# Explicit owner-approved website access; this script requires an elevated PowerShell.
$ErrorActionPreference = 'Stop'
$networkRuleName = 'SteelFrontier-Web-3091'
$networkConfigPath = Join-Path (Split-Path -Parent $PSScriptRoot) '../local/web/runtime/network.json'
$networkConfig = Get-Content -LiteralPath $networkConfigPath -Raw | ConvertFrom-Json
if ($networkConfig.schemaVersion -ne 'web-network.v1' -or $networkConfig.port -ne 3091) { throw 'Unexpected network configuration' }
$networkAdmin = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $networkAdmin.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Run this one-time script in an elevated PowerShell to add the specific TCP3091 rule' }
$networkNode = (Get-Command node -ErrorAction Stop).Source
$existingNetworkRule = Get-NetFirewallRule -Name $networkRuleName -ErrorAction SilentlyContinue
if ($existingNetworkRule) {
    $existingNetworkRule | Get-NetFirewallPortFilter | Format-List Protocol,LocalPort
    throw 'Rule already exists; inspect it rather than replacing an unknown rule'
}
New-NetFirewallRule -Name $networkRuleName -DisplayName 'Стальной рубеж — веб TCP3091' `
    -Direction Inbound -Action Allow -Protocol TCP -LocalPort 3091 `
    -LocalAddress $networkConfig.localIPv4 -InterfaceAlias $networkConfig.interfaceAlias `
    -Program $networkNode -Profile Private -RemoteAddress Any | Select-Object Name,Enabled,Action,Profile
