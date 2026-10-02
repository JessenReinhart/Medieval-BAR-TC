# Recoil headless smoke probe. Stops after TimeoutSeconds because this scaffold
# has no reliable in-engine end condition yet. Nonzero exit is not itself the verdict.
param(
    [int]$TimeoutSeconds = 15,
    [string]$Engine = "$PSScriptRoot\..\engine\recoil_2026.07.04\spring-headless.exe",
    [string]$Map = "$PSScriptRoot\..\runtime\maps\quicksilver_remake_1.24.sd7"
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path "$PSScriptRoot\..\..").Path
$runtime = Join-Path $root 'tools\runtime'
$game = Join-Path $runtime 'games\Medieval-BAR-TC.sdd'
$enginePath = (Resolve-Path $Engine).Path
$mapPath = (Resolve-Path $Map).Path
New-Item -ItemType Directory -Path $game, (Join-Path $runtime 'maps'), (Join-Path $runtime 'logs') -Force | Out-Null
$mapTarget = Join-Path $runtime 'maps\quicksilver_remake_1.24.sd7'
if ($mapPath -ne $mapTarget) { Copy-Item $mapPath $mapTarget -Force }
# Copy project source into an isolated .sdd. Do not copy downloaded engine or runtime data.
& robocopy $root $game /MIR /XD "$root\.git" "$root\tools" /XF '.gitignore' | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed with code $LASTEXITCODE" }
$script = Join-Path $runtime 'startscript.txt'
Copy-Item (Join-Path $PSScriptRoot 'startscript.txt') $script -Force
$infolog = Join-Path $runtime 'infolog.txt'
Remove-Item $infolog -ErrorAction SilentlyContinue
$arguments = @('--isolation', '--write-dir', $runtime, $script)
Write-Host "Running Recoil 2026.07.04: $enginePath $($arguments -join ' ')"
$process = Start-Process -FilePath $enginePath -ArgumentList $arguments -PassThru -NoNewWindow
$finished = $process.WaitForExit($TimeoutSeconds * 1000)
if (-not $finished) {
    Stop-Process -Id $process.Id -Force
    Write-Host "Stopped after $TimeoutSeconds seconds (probe timeout; not a passing simulation test)."
} else {
    Write-Host "Engine exited with code $($process.ExitCode)."
}
if (Test-Path $infolog) {
    Write-Host "Infolog: $infolog"
    Get-Content $infolog | Select-String -Pattern 'Fatal|Error:|using game|using map|Phase 1:|\[f=[0-9]' | ForEach-Object { Write-Host $_.Line }
} else { throw "No infolog produced: $infolog" }
