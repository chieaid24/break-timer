[CmdletBinding()]
param(
    [switch]$SkipDependencies,
    [switch]$SkipInstaller
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Push-Location $root

try {
    if ($SkipDependencies) {
        $python = (Get-Command python -ErrorAction Stop).Source
    }
    else {
        $python = Join-Path $root ".venv\Scripts\python.exe"
        if (-not (Test-Path $python)) {
            & py -3.12 -m venv .venv
            if ($LASTEXITCODE -ne 0) { throw "Could not create the Python environment" }
        }
        & $python -m pip install --disable-pip-version-check -r requirements-dev.txt
        if ($LASTEXITCODE -ne 0) { throw "Could not install Python dependencies" }
    }

    & $python -m ruff format --check .
    if ($LASTEXITCODE -ne 0) { throw "Formatting check failed" }
    & $python -m ruff check .
    if ($LASTEXITCODE -ne 0) { throw "Lint check failed" }
    & $python -m unittest discover -v
    if ($LASTEXITCODE -ne 0) { throw "Tests failed" }
    & $python scripts\generate_build_assets.py
    if ($LASTEXITCODE -ne 0) { throw "Build asset generation failed" }
    & $python -m PyInstaller --clean --noconfirm tray_app.spec
    if ($LASTEXITCODE -ne 0) { throw "Executable build failed" }

    $executable = Join-Path $root "dist\ProductivityTimer.exe"
    if (-not (Test-Path $executable)) { throw "Executable was not created" }

    if (-not $SkipInstaller) {
        $candidates = @(
            (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
            (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
            (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
        )
        $iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
        if (-not $iscc) {
            $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
            if ($command) { $iscc = $command.Source }
        }
        if (-not $iscc) {
            throw "Inno Setup 6 is required. Run scripts\install-inno.ps1 first."
        }

        & $iscc installer\ProductivityTimer.iss
        if ($LASTEXITCODE -ne 0) { throw "Installer build failed" }
        $installer = Join-Path $root "dist\installer\ProductivityTimer-Setup.exe"
        if (-not (Test-Path $installer)) { throw "Installer was not created" }
    }

    Write-Host "Build completed successfully."
}
finally {
    Pop-Location
}
