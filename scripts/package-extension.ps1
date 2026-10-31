# Package extension/ into a Chrome Web Store ZIP — contents only, no secrets.
#
# Usage (from repo root):  pwsh scripts/package-extension.ps1
# Output:  dist/tabsage-extension-v<version>.zip  (gitignored)
#
# Ships only what the extension needs (manifest at the ZIP root, JS/HTML/CSS,
# icons). Excludes README and source maps. Hard-fails if any .env/.pem or an
# API-key-looking string is present, so a secret can never be uploaded.
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$ext  = Join-Path $root "extension"
$dist = Join-Path $root "dist"

$manifest = Get-Content (Join-Path $ext "manifest.json") -Raw | ConvertFrom-Json
$version  = $manifest.version
$zip      = Join-Path $dist "tabsage-extension-v$version.zip"

New-Item -ItemType Directory -Force -Path $dist | Out-Null
if (Test-Path $zip) { Remove-Item $zip }

# Stage only shippable files (preserving relative paths).
# Use a cross-platform temp root: $env:TEMP is Windows-only and is unset on
# macOS/Linux (where PowerShell uses $TMPDIR or /tmp). GetTempPath() resolves
# correctly on every OS, so Join-Path never receives a null path.
$stage = Join-Path ([System.IO.Path]::GetTempPath()) ("tabsage-pkg-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $stage | Out-Null
# Lock the stage to the owner. On Linux/macOS GetTempPath() is the shared,
# world-traversable /tmp, so without this another local user could read a
# secret copied here in the brief window before a safety gate rejects it.
# (On Windows the per-user temp dir is already ACL-restricted to the user.)
if ($IsLinux -or $IsMacOS) {
  & chmod 700 $stage
  if ($LASTEXITCODE -ne 0) { throw "Could not secure the staging directory: $stage" }
}

try {
  $excludeNames = @("README.md")
  Get-ChildItem -Path $ext -Recurse -File | Where-Object {
    $_.Extension -ne ".map" -and ($excludeNames -notcontains $_.Name)
  } | ForEach-Object {
    $rel  = $_.FullName.Substring($ext.Length + 1)
    $dest = Join-Path $stage $rel
    New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
    Copy-Item $_.FullName $dest
  }

  # Safety gate 1: no secret-like files. Reject every .env* variant (.env,
  # .env.local, .env.production, …), not just a bare ".env" — a leading period
  # does NOT hide a file from the archive on Windows, so any of these would ship.
  $bad = Get-ChildItem -Path $stage -Recurse -File |
    Where-Object { $_.Name -like ".env*" -or $_.Extension -in ".pem", ".key" }
  if ($bad) { throw "Refusing to package: secret-like file(s): $($bad.FullName -join ', ')" }

  # Safety gate 2: no API-key-looking strings. Accept hyphens AND underscores in
  # the key body so OpenAI project keys (sk-proj-...) are caught — the old
  # [A-Za-z0-9] class stopped at the hyphen after "sk".
  $hits = Get-ChildItem -Path $stage -Recurse -File |
    Select-String -Pattern "AIza[0-9A-Za-z_-]{20,}", "sk-[A-Za-z0-9_-]{20,}"
  if ($hits) { throw "Refusing to package: possible API key in $($hits.Path -join ', ')" }

  Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip
}
finally {
  # Always remove the stage — including when a safety gate throws above — so a
  # staged secret never lingers in the shared temp directory.
  Remove-Item -Recurse -Force $stage -ErrorAction SilentlyContinue
}

Write-Host "Built $zip"
Write-Host "Contents:"
# List the archive entries for a final eyeball check.
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::OpenRead($zip).Entries |
  ForEach-Object { "  $($_.FullName)" }
