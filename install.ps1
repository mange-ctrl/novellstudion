# Installerar stil-lab: verifierar Python, skapar startare, kör rökprov.
# Inga paket behöver installeras — allt använder Pythons standardbibliotek.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host ""
Write-Host "  stil-lab" -ForegroundColor Cyan
Write-Host "  --------------------------------------------------" -ForegroundColor DarkGray
Write-Host ""

function Find-Python {
    foreach ($cand in @("python", "py")) {
        $cmd = Get-Command $cand -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        try {
            $ver = & $cand -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        } catch { continue }
        if ($LASTEXITCODE -ne 0 -or -not $ver) { continue }
        $p = $ver.Trim().Split(".")
        if ([int]$p[0] -gt 3 -or ([int]$p[0] -eq 3 -and [int]$p[1] -ge 10)) {
            return @{ Exe = $cand; Version = $ver.Trim() }
        }
    }
    return $null
}

$py = Find-Python
if (-not $py) {
    Write-Host "  Python 3.10 eller nyare hittades inte." -ForegroundColor Red
    Write-Host "  Installera från https://www.python.org/downloads/ och kör om." -ForegroundColor Yellow
    exit 1
}
Write-Host "  Python $($py.Version) hittad ($($py.Exe))" -ForegroundColor Green

# Startare: gör att kommandot kan köras från valfri mapp.
$launcher = Join-Path $root "stil.cmd"
$exeLine = if ($py.Exe -eq "py") { "py -3" } else { $py.Exe }
@"
@echo off
cd /d "%~dp0"
$exeLine -m src.cli %*
"@ | Set-Content -Path $launcher -Encoding ASCII
Write-Host "  Startare skapad: stil.cmd" -ForegroundColor Green

# Rökprov: kräver att indexet finns.
if (-not (Test-Path (Join-Path $root "out\stil.db"))) {
    Write-Host "  Varning: out\stil.db saknas. Kör 'stil build' först." -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "  Rökprov:" -ForegroundColor DarkGray
$output = & $py.Exe -m src.cli stats --db out/stil.db
$code = $LASTEXITCODE
$output | Select-Object -First 4
if ($code -ne 0) {
    Write-Host "  Rökprovet misslyckades (exit $code)." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "  Klart. Prova:" -ForegroundColor Green
Write-Host "    .\stil.cmd search `"regnet mot fonstret`" -k 5"
Write-Host "    .\stil.cmd prompt `"tva personer i en bil pa natten`" -k 3"
Write-Host ""
