Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$venvPython = (Join-Path $projectRoot ".venv\Scripts\python.exe").ToLowerInvariant()
$buildDir = Join-Path $projectRoot "build\nuitka"

$pythonProcesses = Get-Process python -ErrorAction SilentlyContinue
if ($pythonProcesses) {
    foreach ($process in $pythonProcesses) {
        $path = ""
        try {
            $path = $process.Path
        } catch {
            continue
        }

        if ($path -and $path.ToLowerInvariant() -eq $venvPython) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
}

foreach ($name in @("cl", "link", "rc", "mt", "cvtres")) {
    Get-Process $name -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
}

Start-Sleep -Seconds 2

if (Test-Path $buildDir) {
    Remove-Item -Recurse -Force $buildDir
}

Write-Host "Cleaned Windows build state in $projectRoot"
