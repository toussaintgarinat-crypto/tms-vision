# Installation ou mise à jour de TMS Vision sous Windows 10/11 (Docker Desktop) en une commande.
# À lancer dans PowerShell (pas besoin d'être administrateur) :
#
#   irm https://raw.githubusercontent.com/toussaintgarinat-crypto/tms-vision/main/install.ps1 | iex
#
# Avec des options :
#   & ([scriptblock]::Create((irm https://raw.githubusercontent.com/toussaintgarinat-crypto/tms-vision/main/install.ps1))) -WithVideos
#     -WithVideos   génère aussi les vidéos d'étirement (long)
#     -NoStart      prépare tout sans lancer les services
#     -Yes          ne pose aucune question (installe Git / Docker Desktop sans demander)
#     -Version X    installe / met à jour vers la version X (ex. 1.2.0) au lieu de la dernière
#     -Check        dit seulement si une mise à jour est disponible, sans rien modifier
# Variables d'environnement : TMS_VERSION (comme -Version), TMS_DIR (dossier, défaut %USERPROFILE%\tms-vision), TMS_REPO,
#   TMS_DOMAIN, TMS_USER, TMS_PASSWORD (évitent les questions), TMS_WITH_VIDEOS=1, TMS_NO_START=1, TMS_YES=1.
#
# Relançable sans risque : si l'installation existe déjà, c'est une MISE À JOUR (sauvegarde de data\,
# git pull, reconstruction) ; le .env et data\ ne sont jamais écrasés.
param(
    [switch]$WithVideos,
    [switch]$NoStart,
    [switch]$Yes,
    [switch]$Check,
    [string]$Version
)

$ErrorActionPreference = 'Stop'
if ($env:TMS_WITH_VIDEOS -eq '1') { $WithVideos = $true }
if ($env:TMS_NO_START -eq '1') { $NoStart = $true }
if ($env:TMS_YES -eq '1') { $Yes = $true }
if (-not $Version -and $env:TMS_VERSION) { $Version = $env:TMS_VERSION }
$Target = if ($Version) { 'v' + $Version.TrimStart('v') } else { '' }   # 1.2.0 et v1.2.0 sont acceptés

$Repo = if ($env:TMS_REPO) { $env:TMS_REPO } else { 'https://github.com/toussaintgarinat-crypto/tms-vision.git' }
$Dir = if ($env:TMS_DIR) { $env:TMS_DIR } else { Join-Path $HOME 'tms-vision' }

function Ok($m)   { Write-Host "[OK] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "[!]  $m" -ForegroundColor Yellow }
function Step($m) { Write-Host ""; Write-Host "== $m ==" -ForegroundColor Cyan }
function Fail($m) { Write-Host "[X]  $m" -ForegroundColor Red; throw $m }

function Ask([string]$Question, [string]$Default) {
    if ($Yes) { return $Default }
    $answer = Read-Host "$Question [$Default]"
    if ([string]::IsNullOrWhiteSpace($answer)) { return $Default }
    return $answer
}
function Confirm-Step([string]$Question) {
    if ($Yes) { return $true }
    $answer = Read-Host "$Question [o/N]"
    return ($answer -match '^[oOyY]')
}
function Has([string]$Command) { return [bool](Get-Command $Command -ErrorAction SilentlyContinue) }
# Réussite d'une commande native, sans que son message d'erreur n'interrompe le script (PowerShell 5.1).
function Test-Native([scriptblock]$Command) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $Command *> $null; return ($LASTEXITCODE -eq 0) } catch { return $false } finally { $ErrorActionPreference = $previous }
}
# Les commandes natives n'arrêtent pas le script d'elles-mêmes : on vérifie leur code de sortie.
function Run([string]$Label, [scriptblock]$Command) {
    & $Command
    if ($LASTEXITCODE -ne 0) { Fail "$Label a échoué (code $LASTEXITCODE)." }
}

# --- Prérequis ---------------------------------------------------------------------------------
Step 'Prérequis'
if ($PSVersionTable.PSVersion.Major -lt 5) { Fail 'PowerShell 5 ou plus est requis (Windows 10/11).' }

if (-not (Has 'git')) {
    if (-not (Has 'winget')) { Fail 'Git est requis : https://git-scm.com/download/win - installez-le puis relancez.' }
    if (-not (Confirm-Step 'Git est absent. L''installer avec winget ?')) { Fail 'Git est requis : https://git-scm.com/download/win' }
    winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
    if (-not (Has 'git')) { Fail 'Git vient d''être installé : fermez cette fenêtre PowerShell, rouvrez-en une et relancez la commande.' }
}
Ok ((git --version) -replace 'git version ', 'Git ')

if (-not (Has 'docker')) {
    if (-not (Has 'winget')) { Fail 'Docker Desktop est requis : https://docs.docker.com/desktop/setup/install/windows-install/ - installez-le puis relancez.' }
    Warn 'Docker Desktop n''est pas installé.'
    if (-not (Confirm-Step 'L''installer avec winget (nécessite WSL2 ; un redémarrage peut être demandé) ?')) {
        Fail 'Docker Desktop est requis : https://docs.docker.com/desktop/setup/install/windows-install/'
    }
    winget install --id Docker.DockerDesktop -e --source winget --accept-package-agreements --accept-source-agreements
    Fail 'Docker Desktop est installé. Redémarrez Windows si demandé, LANCEZ Docker Desktop (acceptez ses conditions, attendez « Engine running »), puis relancez cette commande.'
}
if (-not (Test-Native { docker info })) {
    Fail 'Docker est installé mais ne répond pas. Lancez Docker Desktop, attendez qu''il indique « Engine running », puis relancez.'
}
if (-not (Test-Native { docker compose version })) { Fail 'Le plugin « docker compose » manque (mettez Docker Desktop à jour).' }
Ok ((docker --version) -replace 'Docker version ', 'Docker ' -replace ',.*', '')

# --- Code --------------------------------------------------------------------------------------
Step 'Code'
function Read-Version([string]$Path) {
    $file = Join-Path $Path 'VERSION'
    if (Test-Path $file) { return (Get-Content $file -Raw).Trim() } else { return 'inconnue' }
}
$Update = $false
if (Test-Path (Join-Path $Dir '.git')) {
    $Update = $true
    $CurrentVersion = Read-Version $Dir
    $CurrentCommit = (git -C $Dir rev-parse HEAD).Trim()
    Run 'git fetch' { git -C $Dir fetch --tags --quiet origin main }
    if ($Target) {
        if (-not (Test-Native { git -C $Dir rev-parse -q --verify "refs/tags/$Target" })) {
            Fail "Version $Target introuvable. Versions publiées : $((git -C $Dir tag -l 'v*') -join ' ')"
        }
        $Ref = "refs/tags/$Target"
    } else {
        $Ref = 'origin/main'
    }
    $NewVersion = ((git -C $Dir show "${Ref}:VERSION" 2>$null) | Out-String).Trim()
    if (-not $NewVersion) { $NewVersion = 'inconnue' }
    $NewCommit = (git -C $Dir rev-parse "${Ref}^{commit}").Trim()
    Ok "Installée : version $CurrentVersion ; cible : version $NewVersion"
    if ($Check) {
        if ($CurrentCommit -eq $NewCommit) { Ok 'À jour.' } else {
            Warn "Mise à jour disponible : $CurrentVersion -> $NewVersion. Nouveautés :"
            git -C $Dir log --format='  - %s' "$CurrentCommit..$NewCommit" | Select-Object -First 20
            Write-Host 'Pour l''appliquer : relancer cette commande sans -Check.'
        }
        return
    }
    if (git -C $Dir status --porcelain --untracked-files=no) {
        Fail "Des fichiers du dépôt ont été modifiés dans $Dir : annulez-les (git -C $Dir status) avant la mise à jour."
    }
    if (Test-Path (Join-Path $Dir 'data')) {
        try { & (Join-Path $Dir 'deploy\backup.ps1') } catch { Warn 'Sauvegarde impossible (on continue).' }
    }
    if ($Target) {
        Run "Passage à la version $Target" { git -C $Dir checkout --quiet $Target }
    } else {
        Run 'Mise à jour' { git -C $Dir checkout --quiet main }
        Run 'Mise à jour' { git -C $Dir merge --ff-only --quiet origin/main }
    }
    Ok "Code en version $(Read-Version $Dir)"
} else {
    if ($Check) { Fail "Aucune installation dans $Dir : rien à vérifier." }
    if ((Test-Path $Dir) -and (Get-ChildItem $Dir -Force | Select-Object -First 1)) {
        Fail "$Dir existe et n'est pas vide : choisissez un autre dossier (`$env:TMS_DIR = '...')."
    }
    Run 'git clone' { git clone $Repo $Dir }
    if ($Target) {
        if (-not (Test-Native { git -C $Dir checkout --quiet $Target })) {
            Fail "Version $Target introuvable. Versions publiées : $((git -C $Dir tag -l 'v*') -join ' ')"
        }
    }
    Ok "Code récupéré dans $Dir (version $(Read-Version $Dir))"
}
Set-Location $Dir

# --- Configuration (.env) ----------------------------------------------------------------------
Step 'Configuration'
if (Test-Path '.env') {
    Ok '.env déjà présent : conservé tel quel'
} else {
    # Adresse du site : un nom de domaine, une adresse IP ou « localhost » (pas un numéro de port).
    while ($true) {
        $Domain = if ($env:TMS_DOMAIN) { $env:TMS_DOMAIN } else { Ask 'Adresse du site (nom de domaine, ou localhost pour un essai)' 'localhost' }
        $Domain = ($Domain -replace '^https?://', '') -replace '/.*$', ''
        if (($Domain -match '^[A-Za-z0-9.-]+$') -and ($Domain -notmatch '^[0-9]+$')) { break }
        Warn "« $Domain » n'est pas une adresse valide : tapez un nom de domaine (tms.client.fr), une adresse IP ou localhost (pas un numéro de port)."
        if ($env:TMS_DOMAIN -or $Yes) { Fail 'Adresse du site invalide.' }
    }
    $UserName = if ($env:TMS_USER) { $env:TMS_USER } else { Ask 'Identifiant du praticien' 'praticien' }
    $Password = $env:TMS_PASSWORD
    $Generated = $false
    if (-not $Password -and -not $Yes) {
        $secure = Read-Host 'Mot de passe du praticien (vide = en générer un)' -AsSecureString
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try { $Password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    }
    if (-not $Password) {
        $chars = [char[]]('abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789')
        $Password = -join (1..16 | ForEach-Object { $chars[[Security.Cryptography.RandomNumberGenerator]::GetInt32($chars.Length)] })
        $Generated = $true
    }
    if ($Password.Contains("'")) { Fail 'Le mot de passe ne doit pas contenir d''apostrophe.' }

    $Hash = (& docker run --rm caddy:2-alpine caddy hash-password --plaintext $Password | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $Hash.StartsWith('$2')) { Fail "Impossible de hacher le mot de passe (image caddy:2-alpine ?). Reçu : $Hash" }

    $SiteUrl = "https://$Domain"
    $lines = foreach ($line in (Get-Content '.env.example')) {
        if     ($line -match '^TMS_SITE_ADDRESS=')    { "TMS_SITE_ADDRESS=$Domain" }
        elseif ($line -match '^TMS_SITE_URL=')        { "TMS_SITE_URL=$SiteUrl" }
        elseif ($line -match '^TMS_BASIC_AUTH_USER=') { "TMS_BASIC_AUTH_USER=$UserName" }
        elseif ($line -match '^TMS_BASIC_AUTH_HASH=') { "TMS_BASIC_AUTH_HASH='$Hash'" }
        else   { $line }
    }
    # UTF-8 sans BOM et fins de ligne LF : un BOM en tête de .env fausserait le nom de la 1re variable.
    [IO.File]::WriteAllText((Join-Path (Get-Location) '.env'), (($lines -join "`n") + "`n"), (New-Object Text.UTF8Encoding($false)))
    Ok ".env créé (site : $SiteUrl, identifiant : $UserName)"
    if ($Generated) {
        Write-Host ""
        Write-Host "Mot de passe généré : $Password" -ForegroundColor White
        Write-Host "Notez-le maintenant : il n'est pas conservé en clair (seul son hash est dans .env)."
    }
}

if ($NoStart) {
    Write-Host ""
    Ok "Préparation terminée (-NoStart). Lancer avec : cd $Dir ; docker compose up -d --build"
    return
}

# --- Lancement ---------------------------------------------------------------------------------
Step 'Construction et lancement (première fois : 10 à 20 minutes)'
Run 'docker compose up' { docker compose up -d --build }

Write-Host 'Attente que les services soient prêts...'
for ($i = 0; $i -lt 60; $i++) {
    $states = @(docker compose ps --format '{{.Health}}') | Where-Object { $_ -and $_ -ne 'healthy' }
    if (-not $states) { break }
    Start-Sleep -Seconds 5
}
docker compose ps

if ($WithVideos) {
    Step 'Vidéos d''étirement'
    Run 'La génération des vidéos' { docker compose run --rm capsules }
}

$Site = ((Get-Content '.env' | Where-Object { $_ -match '^TMS_SITE_URL=' } | Select-Object -First 1) -split '=', 2)[1]
# Journal des versions installées sur cette machine (date | version | commit | action).
$Now = Read-Version (Get-Location).Path
$Action = if ($Update) { 'mise-a-jour' } else { 'installation' }
Add-Content -Path '.tms-updates.log' -Value ("{0} | {1} | {2} | {3}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Now, (git rev-parse --short HEAD).Trim(), $Action)
Write-Host ""
if ($Update) { Ok "Mise à jour terminée : version $Now." } else { Ok "Installation terminée : version $Now." }
Write-Host "Site : $Site"
if (-not $WithVideos) { Write-Host "Vidéos d'étirement (à faire une fois) : cd $Dir ; docker compose run --rm capsules" }
Write-Host "Sauvegarde : cd $Dir ; .\deploy\backup.ps1      Guide complet : $Dir\docs\INSTALLATION-CLIENT.md"
