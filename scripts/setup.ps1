param(
    [string]$PythonExe = 'D:\Suriya\tools\python\python.exe',
    [string]$VenvPath = '.venv',
    [switch]$SkipInstall
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if (-not $pythonCommand) {
            throw "Python 3.11 or newer was not found. Install Python or pass -PythonExe."
        }
        $PythonExe = $pythonCommand.Source
    }

    & $PythonExe -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'
    if ($LASTEXITCODE -ne 0) {
        throw 'EIVA requires Python 3.11 or newer.'
    }

    $venvFullPath = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $VenvPath))
    $venvPython = Join-Path $venvFullPath 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
        & $PythonExe -m venv $venvFullPath
        if ($LASTEXITCODE -ne 0) {
            throw 'Could not create the project virtual environment.'
        }
    }

    if (-not $SkipInstall) {
        & $venvPython -m pip install -r (Join-Path $repoRoot 'requirements.txt')
        if ($LASTEXITCODE -ne 0) {
            throw 'Dependency installation failed. Review the pip output and retry.'
        }
    }

    New-Item -ItemType Directory -Force -Path (Join-Path $repoRoot 'data\knowledge') | Out-Null
    Write-Host "EIVA environment is ready at $venvFullPath"
    if (-not (Test-Path -LiteralPath (Join-Path $repoRoot '.env'))) {
        Write-Host 'Create a private .env file and set GROQ_API_KEY before starting the API. See README.md.'
    }
    if ($SkipInstall) {
        Write-Host 'Dependency installation was skipped.'
    }
}
finally {
    Pop-Location
}
