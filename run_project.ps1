param(
    [ValidateSet('demo','acceptance','run','generate-data','check-data')]
    [string]$Command = 'acceptance'
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venv = Join-Path $root '.venv'
$python = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    $created = $false
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        & $launcher.Source -3.11 -m venv $venv
        $created = ($LASTEXITCODE -eq 0) -and (Test-Path -LiteralPath $python)
    }
    if (-not $created) {
        $systemPython = Get-Command python -ErrorAction SilentlyContinue
        if ($systemPython) {
            & $systemPython.Source -m venv $venv
            $created = ($LASTEXITCODE -eq 0) -and (Test-Path -LiteralPath $python)
        }
    }
    if (-not $created) { throw 'Unable to create .venv. Install Python 3.11 or newer first.' }
    & $python -m pip install --disable-pip-version-check -r (Join-Path $root 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Failed to install QualityTrace dependencies.' }
}
$env:PYTHONPATH = Join-Path $root 'src'
& $python -m qualitytrace.cli $Command
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
