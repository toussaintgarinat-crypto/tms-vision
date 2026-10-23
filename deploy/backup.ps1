# Sauvegarde du dossier data\ (base d'analyses DuckDB + vidéos d'exercice) dans une archive datée.
#
#   .\deploy\backup.ps1 [dossier-de-destination]    (défaut : .\backups, ou TMS_BACKUP_DIR dans .env)
#
# Même format que deploy/backup.sh (tar.gz, avec le tar fourni par Windows 10/11) : une archive faite
# sous Windows se restaure sous Linux et inversement. Les 14 dernières archives sont conservées
# (TMS_BACKUP_KEEP pour changer). Copiez aussi les archives HORS du PC (disque externe, NAS...).
param([string]$Destination)
$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

# Valeurs du .env (TMS_BACKUP_DIR, TMS_BACKUP_KEEP), sans exécuter le fichier.
$envValues = @{}
if (Test-Path '.env') {
    foreach ($line in Get-Content '.env') {
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') { $envValues[$Matches[1]] = $Matches[2].Trim("'", '"') }
    }
}
if (-not $Destination) { $Destination = if ($envValues['TMS_BACKUP_DIR']) { $envValues['TMS_BACKUP_DIR'] } else { Join-Path $Root 'backups' } }
$Keep = if ($envValues['TMS_BACKUP_KEEP']) { [int]$envValues['TMS_BACKUP_KEEP'] } else { 14 }

if (-not (Test-Path 'data')) { throw "Aucun dossier data\ à sauvegarder dans $Root." }
if (-not (Get-Command tar -ErrorAction SilentlyContinue)) { throw 'La commande tar est introuvable (Windows 10 version 1803 ou plus récent requis).' }
New-Item -ItemType Directory -Force -Path $Destination | Out-Null

$Archive = Join-Path $Destination ("tms-data-{0}.tar.gz" -f (Get-Date -Format 'yyyy-MM-dd_HHmmss'))
$Partial = "$Archive.tmp"
tar -czf $Partial -C $Root data
if ($LASTEXITCODE -ne 0) { throw 'La création de l''archive a échoué.' }
tar -tzf $Partial *> $null   # l'archive doit se relire en entier
if ($LASTEXITCODE -ne 0) { Remove-Item $Partial -Force; throw 'L''archive créée est illisible.' }
Move-Item $Partial $Archive
Write-Host ("Sauvegarde créée : {0} ({1:N1} Mo)" -f $Archive, ((Get-Item $Archive).Length / 1MB))

# Rotation : on ne garde que les $Keep plus récentes.
Get-ChildItem $Destination -Filter 'tms-data-*.tar.gz' | Sort-Object LastWriteTime -Descending | Select-Object -Skip $Keep | ForEach-Object {
    Remove-Item $_.FullName -Force
    Write-Host "Ancienne sauvegarde supprimée : $($_.FullName)"
}
