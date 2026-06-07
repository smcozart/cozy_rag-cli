# Scaffold a new RAG project from the methodology template.
# Usage: .\scripts\new-project.ps1 -Target D:\dev\my-rag-project [-Name my-rag-project]
param(
    [Parameter(Mandatory = $true)][string]$Target,
    [string]$Name
)

$ErrorActionPreference = "Stop"
$kitRoot = Split-Path -Parent $PSScriptRoot
if (-not $Name) { $Name = Split-Path -Leaf $Target }

if (Test-Path $Target) {
    if (Get-ChildItem $Target -Force | Select-Object -First 1) {
        throw "Target exists and is not empty: $Target"
    }
} else {
    New-Item -ItemType Directory -Path $Target | Out-Null
}

Copy-Item -Recurse -Path (Join-Path $kitRoot "template\*") -Destination $Target
Copy-Item -Path (Join-Path $kitRoot "METHODOLOGY.md") -Destination $Target
Copy-Item -Path (Join-Path $kitRoot "CHECKLIST.md") -Destination $Target

# Stamp the project name into the scaffolded artifacts
foreach ($file in @("DECISIONS.md", "EXPERIMENTS.md", "rag-spec.yaml")) {
    $path = Join-Path $Target $file
    (Get-Content $path -Raw) -replace "<project>", $Name | Set-Content $path -NoNewline
}

New-Item -ItemType Directory -Path (Join-Path $Target "evals\runs") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $Target "data") -Force | Out-Null

Push-Location $Target
git init | Out-Null
Pop-Location

Write-Host "Scaffolded '$Name' at $Target"
Write-Host "Next: Phase 0 — open DECISIONS.md and CHECKLIST.md. Harness: pip install rag-method (or uv add)."
