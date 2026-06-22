#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Expose the AutoCoach API to devices on the local WLAN.

.DESCRIPTION
    WSL2 runs behind a virtual NAT adapter with a dynamic IP. This script:
      1. Discovers the current WSL2 IP and the active WLAN adapter IP.
      2. Removes any stale portproxy rule for port 8000.
      3. Adds a new portproxy rule: Windows WLAN IP:8000 -> WSL2 IP:8000.
      4. Adds (or verifies) a Windows Firewall inbound rule for port 8000.

    Re-run after every WSL2 restart because the WSL2 IP changes each time.
    The firewall rule is permanent and only needs to be added once.

.PARAMETER Port
    The port to expose. Defaults to 8000.

.EXAMPLE
    .\wlan-expose.ps1
    .\wlan-expose.ps1 -Port 3000
#>

param(
    [int]$Port = 8000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# 1. Discover WSL2 IP
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "==> Detecting WSL2 IP..." -ForegroundColor Cyan

$wslIp = (wsl hostname -I 2>$null).Trim().Split(" ")[0]

if (-not $wslIp) {
    Write-Error "Could not detect WSL2 IP. Is WSL2 running? Try: wsl --list --running"
    exit 1
}

Write-Host "    WSL2 IP: $wslIp" -ForegroundColor Green

# ---------------------------------------------------------------------------
# 2. Discover WLAN adapter IP
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "==> Detecting WLAN adapter IP..." -ForegroundColor Cyan

$wlanIp = Get-NetIPAddress -AddressFamily IPv4 `
    | Where-Object { $_.InterfaceAlias -match "Wi-?Fi|WLAN|Wireless" -and $_.IPAddress -ne "127.0.0.1" } `
    | Select-Object -ExpandProperty IPAddress -First 1

if (-not $wlanIp) {
    Write-Warning "No active Wi-Fi adapter found. Listing all IPv4 adapters:"
    Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -ne "127.0.0.1" } `
        | Format-Table InterfaceAlias, IPAddress -AutoSize
    Write-Error "Set wlanIp manually and re-run, or check that Wi-Fi is connected."
    exit 1
}

Write-Host "    WLAN IP:  $wlanIp" -ForegroundColor Green

# ---------------------------------------------------------------------------
# 3. portproxy: remove stale rule, add fresh one
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "==> Configuring portproxy (port $Port)..." -ForegroundColor Cyan

# Remove any existing rule for this port (ignore errors if none exists)
netsh interface portproxy delete v4tov4 `
    listenport=$Port listenaddress=0.0.0.0 2>$null | Out-Null

netsh interface portproxy add v4tov4 `
    listenport=$Port `
    listenaddress=0.0.0.0 `
    connectport=$Port `
    connectaddress=$wslIp

Write-Host "    portproxy: 0.0.0.0:$Port -> ${wslIp}:$Port" -ForegroundColor Green

# ---------------------------------------------------------------------------
# 4. Firewall rule (idempotent - skip if already present)
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "==> Configuring Windows Firewall..." -ForegroundColor Cyan

$ruleName = "AutoCoach-API-Port-$Port"
$existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue

if ($existing) {
    Write-Host "    Firewall rule already exists - skipping." -ForegroundColor Yellow
} else {
    New-NetFirewallRule `
        -DisplayName $ruleName `
        -Direction Inbound `
        -Protocol TCP `
        -LocalPort $Port `
        -Action Allow `
        -Profile Any `
        | Out-Null
    Write-Host "    Firewall rule created: $ruleName" -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# 5. Summary
# ---------------------------------------------------------------------------

Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  AutoCoach API is accessible on your WLAN:" -ForegroundColor White
Write-Host ""
Write-Host "    http://${wlanIp}:$Port" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Re-run this script after restarting WSL2 (the WSL2 IP" -ForegroundColor Gray
Write-Host "  changes on each restart; the firewall rule persists)." -ForegroundColor Gray
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""
