[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($env:CI -ne "true") {
    throw "This destructive installer smoke test may run only in CI."
}

$root = Split-Path -Parent $PSScriptRoot
$installer = Join-Path $root "dist\installer\ProductivityTimer-Setup.exe"
$installDir = Join-Path $env:LOCALAPPDATA "Programs\ProductivityTimer"
$installedExe = Join-Path $installDir "ProductivityTimer.exe"
$uninstaller = Join-Path $installDir "unins000.exe"
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$stateDir = Join-Path $env:LOCALAPPDATA "ProductivityTimer"
$arguments = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-")

if (-not (Test-Path $installer)) { throw "Installer was not found" }

try {
    $install = Start-Process $installer -ArgumentList $arguments -Wait -PassThru
    if ($install.ExitCode -ne 0) {
        throw "Installer exited with code $($install.ExitCode)"
    }
    if (-not (Test-Path $installedExe)) { throw "Installed app was not found" }
    if (-not (Test-Path $uninstaller)) { throw "Uninstaller was not found" }

    $startup = Get-ItemPropertyValue -Path $runKey -Name "ProductivityTimer"
    $expectedStartup = '"' + $installedExe + '"'
    if ($startup -ne $expectedStartup) {
        throw "Startup entry was '$startup' instead of '$expectedStartup'"
    }

    New-Item -Path $stateDir -ItemType Directory -Force | Out-Null
    Set-Content -Path (Join-Path $stateDir "smoke-test.txt") -Value "test"
}
finally {
    if (Test-Path $uninstaller) {
        $uninstall = Start-Process $uninstaller -ArgumentList $arguments -Wait -PassThru
        if ($uninstall.ExitCode -ne 0) {
            throw "Uninstaller exited with code $($uninstall.ExitCode)"
        }
    }
}

if (Test-Path $installedExe) { throw "Installed app remained after uninstall" }
if (Test-Path $stateDir) { throw "App data remained after uninstall" }
$registry = Get-ItemProperty -Path $runKey -ErrorAction SilentlyContinue
if ($registry -and $registry.PSObject.Properties["ProductivityTimer"]) {
    throw "Startup entry remained after uninstall"
}

Write-Host "Installer smoke test completed successfully."
