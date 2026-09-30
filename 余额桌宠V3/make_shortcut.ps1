# Balance Pet V3 - create a desktop shortcut.
# Called by the "create shortcut" .bat, or run it yourself:
#     powershell -NoProfile -ExecutionPolicy Bypass -File make_shortcut.ps1
#
# ASCII only on purpose: PowerShell 5.1 reads BOM-less UTF-8 files as ANSI,
# so any CJK literal here would turn into mojibake. The shortcut name is
# taken from the folder name instead of being hard coded.
#
# Optional -OutDir picks the output folder (used for testing).

param(
    [string]$OutDir = ''
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$name = Split-Path -Leaf $root

$vbs = Get-ChildItem -LiteralPath $root -Filter '*.vbs' -File |
       Select-Object -First 1
if ($null -eq $vbs) {
    Write-Host "[ERROR] no .vbs launcher found in $root" -ForegroundColor Red
    exit 1
}

$icon = Join-Path $root 'assets\pet.ico'
if (-not $OutDir) { $OutDir = [Environment]::GetFolderPath('Desktop') }
if (-not (Test-Path -LiteralPath $OutDir)) {
    New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
}
$lnk = Join-Path $OutDir ($name + '.lnk')

try {
    $shell = New-Object -ComObject WScript.Shell
    $sc = $shell.CreateShortcut($lnk)
    $sc.TargetPath       = Join-Path $env:SystemRoot 'System32\wscript.exe'
    $sc.Arguments        = '//nologo "' + $vbs.FullName + '"'
    $sc.WorkingDirectory = $root
    if (Test-Path $icon) {
        $sc.IconLocation = "$icon,0"
    } else {
        $sc.IconLocation = "$env:SystemRoot\System32\shell32.dll,44"
    }
    $sc.Description = 'Balance Pet V3 - DeepSeek balance desktop widget'
    $sc.Save()

    if (Test-Path $lnk) {
        Write-Host "[OK] shortcut created:" -ForegroundColor Green
        Write-Host "     $lnk"
        exit 0
    }
    Write-Host "[ERROR] the .lnk file was not created" -ForegroundColor Red
    exit 2
}
catch {
    Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
    exit 3
}
