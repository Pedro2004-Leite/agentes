# Agentes Diários

Sistema de agentes AI para OpenClaw. Cada agente vive na sua própria pasta com ficheiros markdown que definem personalidade, regras, ferramentas e preferências.

## Estrutura do projeto

```
agentes/
├── _template/              ← Molde para criar novos agentes
├── organizador-diario/     ← Agente de produtividade pessoal
├── analista-financeiro/    ← Agente de análise financeira
├── setup.ps1               ← Script pós-clone (mostra estado e próximos passos)
├── novo-agente.ps1         ← Cria novo agente a partir do _template
├── CLAUDE.md               ← Este ficheiro
└── README.md               ← Documentação completa
```

## Ficheiros de cada agente

| Ficheiro | Função |
|----------|--------|
| `SOUL.md` | Personalidade, tom, identidade do agente |
| `AGENTS.md` | Regras de comportamento, ferramentas permitidas, workflow |
| `USER.md` | Preferências do utilizador (objetivos, hábitos, ferramentas) |
| `IDENTITY.md` | Nome, emoji, vibe, avatar do agente |
| `TOOLS.md.example` | Template de config local — copiar para `TOOLS.md` |
| `HEARTBEAT.md` | Tarefas agendadas periódicas |

`TOOLS.md` está no `.gitignore` — cada máquina tem o seu.

## Agentes ativos

### 📋 Organizador Diário (`organizador-diario/`)
- Gerido pelo OpenClaw em `C:\Creative\agents\organizador-diario`
- Ajuda com produtividade: priorização matinal (3 tarefas), blocos de tempo, retrospectiva
- Utilizador: estudante, Portugal, foco em autonomia financeira e eficiência
- Tom: curto, direto, caloroso

### 📈 Analista Financeiro (`analista-financeiro/`)
- Scripts Python em `scripts/`:
  - `market_briefing.py` — briefing matinal de mercados (índices, notícias, watchlist)
  - `stock_analysis.py <TICKER>` — análise completa estilo relatório profissional (fundamental + técnica + valuation + bull/bear)
  - `screener.py` — screening técnico (RSI, MACD, volume, SMA)
- Dependências: `pip install yfinance pandas numpy tabulate`
- Perfil: trading ativo, análise técnica, sem portefólio fixo
- A metodologia de análise segue o relatório NBIS.pdf (DCF, peer comparison, níveis técnicos)
- Output em `reports/` (gitignored)

## OpenClaw

O OpenClaw está em `C:\Creative\openclaw\`. A config local (`openclaw.local.json`) aponta para os workspaces dos agentes.

```json
{
  "agents": {
    "defaults": {
      "workspace": "C:/Creative/agents/organizador-diario"
    }
  }
}
```

Para adicionar o analista-financeiro, criar uma entry no array `agents` com o workspace correspondente.

## Criar novo agente

```powershell
.\novo-agente.ps1 <slug> "Nome Bonito"
```

Depois editar os ficheiros na nova pasta.

## Convenções

- Tudo em Português de Portugal
- Respostas curtas e diretas
- Cada agente tem no máximo 3 prioridades por dia
- Foco no que é acionável, sem ruído
