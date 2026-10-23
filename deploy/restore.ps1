# Restaure data\ depuis une archive créée par deploy/backup.ps1 (ou backup.sh).
#
#   .\deploy\restore.ps1 <archive.tar.gz>
#
# Arrêtez le site avant : docker compose stop api web. Le data\ actuel n'est pas détruit : il est mis
# de côté sous le nom data.avant-restauration-<date>.
param([Parameter(Mandatory = $true)][string]$Archive)
$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path $Archive)) { throw "Archive introuvable : $Archive" }
$Archive = (Resolve-Path $Archive).Path
$listing = tar -tzf $Archive
if ($LASTEXITCODE -ne 0) { throw "Archive illisible : $Archive" }
if (-not ($listing | Where-Object { $_ -like 'data/*' } | Select-Object -First 1)) { throw 'Cette archive ne contient pas de dossier data/.' }

if (Test-Path 'data') {
    $aside = 'data.avant-restauration-{0}' -f (Get-Date -Format 'yyyyMMdd_HHmmss')
    Move-Item 'data' $aside
    Write-Host "data\ actuel mis de côté : $aside"
}
tar -xzf $Archive -C $Root
if ($LASTEXITCODE -ne 0) { throw 'L''extraction a échoué.' }
Write-Host "Restauration terminée depuis $Archive. Relancez le site : docker compose start api web"
