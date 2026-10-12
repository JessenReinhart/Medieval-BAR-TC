# Launch Medieval-BAR-TC as an interactive (windowed) match.
# Syncs the mod sources into the isolated runtime .sdd, ensures the map is
# present, and starts the Recoil engine in windowed mode with a human player
# (Team 0) versus a NullAI opponent (Team 1).
param(
    [string]$Engine = "$PSScriptRoot\..\engine\recoil_2026.07.04\spring.exe",
    [string]$Map = "$PSScriptRoot\..\runtime\maps\quicksilver_remake_1.24.sd7",
    [string]$Script = "$PSScriptRoot\startscript_play.txt"
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path "$PSScriptRoot\..\..").Path
$runtime = Join-Path $root 'tools\runtime'
$game = Join-Path $runtime 'games\Medieval-BAR-TC.sdd'
$enginePath = (Resolve-Path $Engine).Path
$mapPath = (Resolve-Path $Map).Path
$scriptPath = (Resolve-Path $Script).Path

# 1. Refresh the isolated mod directory from the current sources.
New-Item -ItemType Directory -Path $game, (Join-Path $runtime 'maps') -Force | Out-Null
& robocopy $root $game /MIR /XD "$root\.git" "$root\tools" /XF '.gitignore' | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed with code $LASTEXITCODE" }

# 2. Ensure the map is available in the runtime.
$mapTarget = Join-Path $runtime 'maps\quicksilver_remake_1.24.sd7'
if ($mapPath -ne $mapTarget) { Copy-Item $mapPath $mapTarget -Force }

# 3. Install the play startscript.
$scriptTarget = Join-Path $runtime 'script.txt'
Copy-Item $scriptPath $scriptTarget -Force

# 4. Launch the windowed engine. Do not pass --isolation: that forces the
#    headless-style isolated session used by CI probes.
Write-Host "Launching Recoil: $enginePath --write-dir $runtime $scriptTarget"
Start-Process -FilePath $enginePath -ArgumentList @('--write-dir', $runtime, $scriptTarget)