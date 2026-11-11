$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    $python = Join-Path $repoRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw 'Project environment is missing. Run scripts\setup.ps1 first.'
    }

    $checks = @(
        @('-m', 'unittest', 'discover', '-s', 'tests'),
        @('-m', 'scripts.verify_tool_policies'),
        @('-m', 'scripts.verify_orchestration'),
        @('-m', 'scripts.evaluate_runtime_m00_m07'),
        @('-m', 'scripts.evaluate_persistence'),
        @('-m', 'scripts.evaluate_rag'),
        @('-m', 'compileall', '-q', 'backend', 'scripts', 'tests'),
        @('-m', 'pip', 'check')
    )
    foreach ($check in $checks) {
        Write-Host "`n> $python $($check -join ' ')" -ForegroundColor Cyan
        & $python @check
        if ($LASTEXITCODE -ne 0) {
            throw "Release check failed: $($check -join ' ')"
        }
    }

    $node = Get-Command node -ErrorAction SilentlyContinue
    if ($node) {
        Write-Host "`n> node --test tests/test_frontend_stream.mjs" -ForegroundColor Cyan
        & $node.Source --test (Join-Path $repoRoot 'tests\test_frontend_stream.mjs')
        if ($LASTEXITCODE -ne 0) {
            throw 'Frontend stream tests failed.'
        }
    }
    else {
        Write-Warning 'Node.js was not found; frontend stream tests were skipped. The app itself has no Node build step.'
    }

    & $python -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('pip_audit') else 1)"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`n> pip-audit" -ForegroundColor Cyan
        & $python -m pip_audit
        if ($LASTEXITCODE -ne 0) {
            throw 'Dependency advisory audit failed.'
        }
    }
    else {
        Write-Warning 'pip-audit is not installed; dependency advisory scanning remains a release follow-up.'
    }

    Write-Host "`nEIVA local release checks passed." -ForegroundColor Green
}
finally {
    Pop-Location
}
