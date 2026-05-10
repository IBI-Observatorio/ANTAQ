# h=1 (mensal) — arquivado, não publicado

**Status:** falha do critério forte de Linha D pré-registrado.
**Decisão:** 2026-05-04. Ver
[`../REGRA_LANCAMENTO.md`](../REGRA_LANCAMENTO.md) seção
"ADENDO POST-RESULTADO" para a interpretação completa.

Este diretório existe para **transparência metodológica**: os artefatos
do horizonte mensal estão preservados intactos para auditoria, mesmo que
o indicador correspondente **não** seja publicado no observatório.
Suprimir os números seria contra a disciplina anti-garimpagem do
pré-registro.

## Por que h=1 não foi publicado

| Critério | Valor observado | Limiar pré-registrado | Resultado |
|---|---|---|---|
| `w_DFM` médio rolling OOS | **15,5%** | ≥ 25% | Falha (no piso da banda) |
| `w_DFM` mediana | 15,6% | — | Estável mas baixa |
| MAE_combinação vs MAE_AR(1) | 2,02 vs 2,06 (Δ −0,04 pp) | < AR(1) | Numericamente sim |
| DM-HLN combinação vs AR(1) | p = **0,64** | (poder informativo) | Indistinguível de zero |
| Encompassing `AR(1) -> DFM-1f` | λ = 0,18, p = **0,10** | rejeição clara | Borderline |

A combinação numericamente bate o AR(1) por 0,04 pp em MAE, mas:

1. O peso ótimo está no **piso** da banda definida (15,5% vs limiar 15%),
   não há margem de segurança contra erro amostral.
2. O DM-HLN tem `p = 0,64` — a diferença em MAE é estatisticamente
   indistinguível de zero.
3. O encompassing test é borderline (`p = 0,10`); não há evidência clara
   de que o DFM-1f agregue informação que o AR(1) não capture em h=1.

A interpretação inicial do código foi "zona cinza" (15% ≤ w_DFM < 25%),
mas o pré-registro não definiu regra explícita para essa faixa — uma
falha do design original do pré-registro, agora corrigida na
**lição metodológica** registrada na seção ADENDO da regra.

## Arquivos preservados

Todos os artefatos abaixo são fatias de h=1 dos CSVs originais
(que continham h=1 e h=2 misturados):

| Arquivo | Conteúdo |
|---|---|
| `walkforward_dfm_previsoes.csv` | Previsões walk-forward DFM-1f, DFM-2f e AR(1), h=1 |
| `gr_rolling_pesos.csv` | Pesos GR rolling OOS por origem, h=1 |
| `gr_rolling_metricas.csv` | MAE/RMSE da combinação OOS-legítima, h=1 |
| `gr_rolling_dm.csv` | DM-HLN da combinação OOS vs AR(1) e DFM-1f, h=1 |
| `conformal_calibracao.csv` | Erros do conjunto de calibração conformal, h=1 |
| `conformal_intervalos_teste.csv` | Intervalos por método no conjunto de teste, h=1 |
| `conformal_cobertura.csv` | Cobertura empírica + IC95% Wilson, h=1 |
| `dm_completo.csv` | DM-HLN do spike comparativo, h=1 |
| `encompassing.csv` | Encompassing test bidireccional, h=1 |
| `granger_ramanathan.csv` | GR full-sample (in-sample), h=1 |

## Para o re-test 2028

Re-rodar a bateria completa em h=1 conforme
[`../compromisso_retest_2028.md`](../compromisso_retest_2028.md). A
janela amostral expandida pode revelar que o sinal mensal é genuíno
mas faltava poder em 2026 — ou confirmar que h=1 não é defensável.
A regra de decisão atualizada já cobre a faixa 15-25% explicitamente
para evitar nova zona cinza.
