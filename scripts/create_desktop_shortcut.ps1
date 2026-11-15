# scripts/create_desktop_shortcut.ps1
# Creates Desktop Shortcut for Asset Control Tower (v4.8)

$ErrorActionPreference = "Stop"

$pythonExe = "python"
if (Test-Path "C:\Users\pobco\.local\bin\python3.12.exe") {
    $pythonExe = "C:\Users\pobco\.local\bin\python3.12.exe"
}

$scriptPath = Join-Path $PSScriptRoot "create_desktop_shortcut.py"
& $pythonExe $scriptPath
