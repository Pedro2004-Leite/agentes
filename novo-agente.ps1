# novo-agente.ps1 — Cria um novo agente a partir do _template
# Uso: .\novo-agente.ps1 <slug> "Nome Bonito"

param (
    [Parameter(Mandatory=$true, HelpMessage="Slug do agente (ex: revisor-de-habitos)")]
    [string]$Slug,

    [Parameter(Mandatory=$true, HelpMessage="Nome bonito do agente (ex: 'Revisor de Habitos')")]
    [string]$Nome
)

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSCommandPath
$template = Join-Path $raiz "_template"
$destino = Join-Path $raiz $Slug

# Validar
if ($Slug -match '[^a-z0-9\-]') {
    Write-Error "Slug invalido: usa so minusculas, numeros e hifens."
    exit 1
}

if (Test-Path $destino) {
    Write-Error "A pasta '$Slug' ja existe."
    exit 1
}

Write-Host "A criar agente '$Nome' em .\$Slug..." -ForegroundColor Green

# Copiar template
Copy-Item -Path $template -Destination $destino -Recurse

# Substituir placeholders nos ficheiros
Get-ChildItem -Path $destino -File | ForEach-Object {
    $conteudo = Get-Content $_.FullName -Raw -Encoding UTF8
    $conteudo = $conteudo -replace '\[Nome do Agente\]', $Nome
    $conteudo = $conteudo -replace '\[Nome\]', $Nome
    $conteudo = $conteudo -replace '\[uma frase sobre o meu propósito\]', '[uma frase sobre o meu proposito]'
    $conteudo = $conteudo -replace '\[Traço \d\]', '[Tracao]'
    $conteudo = $conteudo -replace '\[Capacidade \d\]', '[Capacidade]'
    $conteudo = $conteudo -replace '\[Regra \d\]', '[Regra]'
    $conteudo = $conteudo -replace '\[Comportamento principal \d\]', '[Comportamento]'
    $conteudo = $conteudo -replace '\[Limite \d\]', '[Limite]'
    $conteudo = $conteudo -replace '\[Descrição do tom — curto e direto\]', '[Descricao do tom]'
    Set-Content -Path $_.FullName -Value $conteudo -Encoding UTF8 -NoNewline
}

Write-Host "Pronto! Agente criado em .\$Slug\" -ForegroundColor Green
Write-Host ""
Write-Host "Proximos passos:" -ForegroundColor Yellow
Write-Host "  1. Edita .\$Slug\SOUL.md       — personalidade e tom"
Write-Host "  2. Edita .\$Slug\AGENTS.md      — regras e ferramentas"
Write-Host "  3. Edita .\$Slug\USER.md        — preferencias do utilizador"
Write-Host "  4. Edita .\$Slug\IDENTITY.md    — nome, emoji, vibe do agente"
Write-Host "  5. Aponta o OpenClaw para .\$Slug\"
