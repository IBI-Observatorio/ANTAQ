# Pipeline PIM-PF Combinado IBI

Infraestrutura mensal de previsão e monitoramento do indicador
**PIM-PF Combinado IBI — componente DFM em horizonte bimestral**.

> Ver pré-registro completo em
> [`validacao/portgdp_v2/REGRA_LANCAMENTO.md`](../../validacao/portgdp_v2/REGRA_LANCAMENTO.md)
> e nota técnica em
> [`docs/nota_tecnica_pimpf_combinado_v1.md`](../../docs/nota_tecnica_pimpf_combinado_v1.md).

---

## Scripts (em ordem de execução)

| Script | O que faz |
|---|---|
| [`fetch_dados.py`](fetch_dados.py) | Snapshot diário de PIM-PF (BCB SGS 28503) e ANTAQ (parquet consolidado), com hash SHA-256 em `data/snapshots/manifest.csv`. |
| [`gera_previsao.py`](gera_previsao.py) | Aplica DFM atual + GR rolling + conformal sobre snapshot mais recente; appenda previsão `t+1` e `t+2` em `data/previsoes/historico.csv` com `tipo=producao`. |
| [`atualiza_realizados.py`](atualiza_realizados.py) | Para previsões antigas cujo `mes_alvo` agora tem dado disponível, preenche `realizado`, `erro`, `dentro_intervalo`. Atualiza `data/previsoes/track_record_producao.csv`. |
| [`verifica_degradacao.py`](verifica_degradacao.py) | Abre issue automática se últimas 3 previsões em produção tiveram erro > 6 pp ou se cobertura empírica saiu de [70%, 95%] após ≥ 6 previsões. |
| [`refit_anual.py`](refit_anual.py) | **Cron separado**, dia 5 de janeiro: re-estima DFM-1f com janela completa, salva `models/dfm_AAAA.pkl`, atualiza `models/dfm_atual.pkl`, loga em `models/refit_log.md`. |
| [`popular_historico.py`](popular_historico.py) | **Inicialização única**: pré-popula `historico.csv` com 12 últimas previsões da janela de validação (jan/2024–out/2025, h=2, `tipo=validacao_historica`). |
| [`orquestrador.sh`](orquestrador.sh) | Roda em sequência fetch → gera → atualiza → verifica. Idempotente. |

---

## Calendário esperado (mês a mês)

| Dia | Ator | Ação |
|---|---|---|
| ~dia 2 | IBGE | Publica PIM-PF do mês t-2 (defasagem ~40 dias) |
| dia 5, 08h UTC | Cron `pimpf_pipeline_mensal.yml` | Roda `orquestrador.sh` |
| dia 5, ~08h15 | Bot | Abre PR `data-update/AAAA-MM` com CSVs novos |
| dia 5–6 | Humano | Revisa PR (24h opcional); auto-merge se sem objeções |
| dia 6 | Site | Próximo build do Observatório IBI puxa novo `historico.csv` e renderiza card atualizado |

Calendário detalhado de releases até mai/2028 em
[`docs/calendario_releases.md`](../../docs/calendario_releases.md).

---

## Operação em emergência (rodar manualmente)

```bash
# Dependências
pip install -r requirements.txt

# Rodar pipeline completo manualmente
bash pipelines/pimpf_combinado/orquestrador.sh

# Ou rodar etapas individuais
python -m pipelines.pimpf_combinado.fetch_dados
python -m pipelines.pimpf_combinado.gera_previsao
python -m pipelines.pimpf_combinado.atualiza_realizados
python -m pipelines.pimpf_combinado.verifica_degradacao

# Pular fetch ANTAQ (debug local)
PULAR_ANTAQ=1 bash pipelines/pimpf_combinado/orquestrador.sh
```

---

## Troubleshooting — cron mensal falhou

Quando o workflow `pimpf_pipeline_mensal.yml` falha, ele abre issue
com label `pipeline-falha`. Checklist do investigador:

1. **BCB SGS 28503** está acessível? `curl -fsSL "https://api.bcb.gov.br/dados/serie/bcdata.sgs.28503/dados/ultimos/12?formato=json" | head` deveria retornar JSON.
2. **Endpoint ANTAQ** está acessível? Testar `https://estatistica.antaq.gov.br/ea/txt/`.
3. **Cache de Parquets ANTAQ** corrompido? Limpar com `rm -rf parquet/` e re-rodar.
4. **DFM `models/dfm_atual.pkl` carregando?** Tentar `python -c "import pickle; pickle.load(open('models/dfm_atual.pkl','rb'))"`. Se falhar, re-rodar `refit_anual.py --force`.
5. **Disco cheio**? Snapshots crescem ~100 MB/mês. Liberar `data/snapshots/` mais antigo se necessário (cuidado para preservar manifest).

---

## Troubleshooting — alerta de degradação disparou

Quando `verifica_degradacao.py` abre issue com label `degradacao-modelo`
ou `cobertura-fora-da-faixa`, **não modifique o status público
automaticamente**. Checklist:

### `degradacao-modelo` (3 erros consecutivos > 6 pp)

1. Verificar se houve choque macroeconômico no período (COVID-like).
2. Conferir se snapshots PIM-PF/ANTAQ estão atualizados.
3. Avaliar se o lag estrutural -2 ainda se sustenta (rolling cross-correlation).
4. Considerar refit anual fora de calendário (`refit_anual.py --force`).
5. Se persistir após 2 ciclos: antecipar discussão do re-test (originalmente mai/2028).

### `cobertura-fora-da-faixa` (cobertura empírica fora [70%, 95%])

1. Re-rodar split conformal padrão com janela atual.
2. Avaliar block-bootstrap.
3. Conferir se houve mudança estrutural na variância dos erros.
4. **Recalibração** é a ação esperada. **Não rebaixar** o indicador
   automaticamente.

---

## Responsabilidades

- **PRs com label `auto-merge-data`**: revisão humana opcional (24h).
  Responsável padrão: @brunodop.
- **Issues com label `pipeline-falha`**: investigar até 48h.
- **Issues com label `degradacao-modelo` / `cobertura-fora-da-faixa`**:
  triagem em até 7 dias; pode levar a issue de re-validação.
- **Refit anual** (5 jan): conferir log em `models/refit_log.md` e
  comparar loadings com refits anteriores. Mudança grande nos loadings
  abre issue de discussão metodológica.

---

## Outputs do pipeline

```
data/
├── snapshots/
│   ├── pimpf/AAAA-MM-DD.csv       # snapshot do PIM-PF naquele dia
│   ├── antaq/AAAA-MM-DD.parquet   # painel das 35 séries naquele dia
│   └── manifest.csv                # log com hash SHA-256
└── previsoes/
    ├── historico.csv               # toda previsão emitida (validação + produção)
    ├── track_record_producao.csv   # métricas em produção (rolling 12m)
    └── logs/orquestrador_AAAA-MM-DD.log
models/
├── dfm_2026.pkl                    # modelo treinado em 2026
├── dfm_atual.pkl                   # ponteiro para o atual
└── refit_log.md
```

---

## Disciplina (não-negociável)

1. **Pipeline nunca modifica conteúdo editorial.** Só mexe em CSVs de
   dados (`data/`) e log de refit.
2. **Disclaimer de vintage** sempre visível no card público.
3. **Separação visual** entre validação histórica e produção na tabela
   de track record.
4. **Imprensa proativa** apenas após ≥ 2 previsões em produção com
   realizado disponível (≈ set/2026).
