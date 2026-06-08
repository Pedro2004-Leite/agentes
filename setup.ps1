# setup.ps1 -- Primeiro uso apos clonar o repo
# Uso: .\setup.ps1

$ErrorActionPreference = "Continue"
$raiz = Split-Path -Parent $PSCommandPath

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Agentes Diarios - Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "  [INFO] PowerShell $($PSVersionTable.PSVersion)" -ForegroundColor Gray

$git = Get-Command git -ErrorAction SilentlyContinue
if ($git) {
    Write-Host "  [OK] Git encontrado" -ForegroundColor Gray
} else {
    Write-Host "  [AVISO] Git nao encontrado - recomendo instalar" -ForegroundColor DarkYellow
}

Write-Host ""
Write-Host "Agentes disponiveis:" -ForegroundColor Green
Get-ChildItem -Path $raiz -Directory -Exclude "_template", ".git" | ForEach-Object {
    $temSoul = Test-Path (Join-Path $_.FullName "SOUL.md")
    $marcador = if ($temSoul) { "[OK]" } else { "[  ]" }
    Write-Host "  $marcador $($_.Name)"
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Proximos passos" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  1. Para cada agente, preenche:" -ForegroundColor Yellow
Write-Host "     - USER.md     (os teus objetivos, habitos, ferramentas)"
Write-Host "     - IDENTITY.md (nome, emoji, vibe do agente)"
Write-Host "     - TOOLS.md    (configuracao especifica da tua maquina)"
Write-Host ""
Write-Host "  2. Criar novo agente:" -ForegroundColor Yellow
Write-Host "     .\novo-agente.ps1 <slug> 'Nome Bonito'"
Write-Host ""
Write-Host "  3. Apontar o OpenClaw para a pasta do agente." -ForegroundColor Yellow
Write-Host ""
