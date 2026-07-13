[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$version = "6.7.3"
$expectedHash = "9c73c3bae7ed48d44112a0f48e66742c00090bdb5bef71d9d3c056c66e97b732"
$installerUrl = "https://github.com/jrsoftware/issrc/releases/download/is-6_7_3/innosetup-6.7.3.exe"
$downloadPath = Join-Path $env:TEMP "innosetup-$version.exe"
$existingInstall = @(
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($existingInstall) {
    Write-Host "Inno Setup is already installed at $existingInstall"
    exit 0
}

Write-Host "Downloading Inno Setup $version from its official release..."
Invoke-WebRequest -Uri $installerUrl -OutFile $downloadPath

$actualHash = (Get-FileHash -Path $downloadPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $expectedHash) {
    Remove-Item $downloadPath -Force
    throw "Inno Setup checksum verification failed"
}

Write-Host "Installing verified Inno Setup $version..."
$process = Start-Process -FilePath $downloadPath -ArgumentList @(
    "/VERYSILENT",
    "/SUPPRESSMSGBOXES",
    "/NORESTART",
    "/SP-"
) -Wait -PassThru
Remove-Item $downloadPath -Force

if ($process.ExitCode -notin @(0, 1641, 3010)) {
    throw "Inno Setup installation failed with exit code $($process.ExitCode)"
}
