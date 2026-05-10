# Itens finais antes do lançamento — sumário executivo

Tempo total de execução: 2.9s

## Item 1 — Granger-Ramanathan rolling OOS

### Estatísticas dos pesos

| h | n_origens_oos | w_dfm_media | w_dfm_mediana | w_dfm_min | w_dfm_max | w_dfm_dp | n_truncamentos |
|---|---|---|---|---|---|---|---|
| 1.000 | 58.000 | 0.155 | 0.156 | 0.063 | 0.235 | 0.023 | 0.000 |
| 2.000 | 58.000 | 0.424 | 0.432 | 0.273 | 0.485 | 0.028 | 0.000 |

### Métricas da combinação OOS-legítima

| h | modelo | n | mae_pp | rmse_pp |
|---|---|---|---|---|
| 1 | comb_oos | 58 | 2.023 | 4.258 |
| 1 | ar1 | 58 | 2.063 | 4.162 |
| 1 | dfm_1f | 58 | 3.504 | 6.575 |
| 2 | comb_oos | 58 | 3.010 | 5.882 |
| 2 | ar1 | 58 | 3.019 | 6.033 |
| 2 | dfm_1f | 58 | 3.492 | 6.543 |

### DM-HLN

| h | comparacao | dm_stat | p_value | n |
|---|---|---|---|---|
| 1 | comb_oos vs ar1 | 0.4650 | 0.6437 | 58 |
| 1 | comb_oos vs dfm_1f | -1.9242 | 0.0593 | 58 |
| 2 | comb_oos vs ar1 | -0.3138 | 0.7548 | 58 |
| 2 | comb_oos vs dfm_1f | -1.3778 | 0.1736 | 58 |

### Decisão Item 1

- **h = 1**: w_DFM médio = 0.155, MAE_comb = 2.02 pp, MAE_AR1 = 2.06 pp → **Zona cinza (15% ≤ w_DFM < 25% e MAE_comb < MAE_AR1)**
- **h = 2**: w_DFM médio = 0.424, MAE_comb = 3.01 pp, MAE_AR1 = 3.02 pp → **Linha D MANTIDA (w_DFM ≥ 25% e MAE_comb < MAE_AR1)**

## Item 2 — Calibração conformal

| metodo | h | n_calibracao | n_teste | nominal | cobertura | largura_pp | desvio_cobertura_pp |
|---|---|---|---|---|---|---|---|
| conformal_padrao | 1 | 29 | 29 | 0.800 | 0.931 | 6.267 | 13.103 |
| conformal_block_bootstrap | 1 | 29 | 29 | 0.800 | 0.966 | 7.315 | 16.552 |
| quantil_empirico_simples | 1 | 29 | 29 | 0.800 | 0.931 | 5.507 | 13.103 |
| conformal_padrao | 2 | 29 | 29 | 0.800 | 1.000 | 10.697 | 20.000 |
| conformal_block_bootstrap | 2 | 29 | 29 | 0.800 | 1.000 | 11.405 | 20.000 |
| quantil_empirico_simples | 2 | 29 | 29 | 0.800 | 1.000 | 10.614 | 20.000 |

### Decisão Item 2

- **h = 1**: método recomendado = `conformal_padrao` (cobertura empírica 93.1%, largura 6.27 pp)
- **h = 2**: método recomendado = `conformal_padrao` (cobertura empírica 100.0%, largura 10.70 pp)

## Status final do lançamento

> **Decisão metodológica final tomada em 2026-05-04 (ver REGRA_LANCAMENTO.md
> seção ADENDO POST-RESULTADO).** A interpretação inicial de "zona cinza"
> em h=1 foi reclassificada como **falha do critério forte de Linha D**.

| h | Status Item 1 | Método conformal | Cobertura empírica (IC95% Wilson) | Largura | Decisão de publicação |
|---|---|---|---|---|---|
| 1 | **FALHA** — w_DFM=15,5% no piso da banda + DM p=0,64 | `conformal_padrao` | 93,1% [78,0%, 98,1%] | 6,27 pp | **NÃO publicado** (h=1) |
| 2 | **Linha D MANTIDA** — w_DFM=42,4%, encompassing simétrico, IC dos pesos robusto | `conformal_padrao` | 100% [88,3%, 100%] | 10,70 pp | **PUBLICADO** como PIM-PF Combinado IBI |

### Justificativa por trás da reclassificação de h=1

1. `w_DFM = 15,5%` está no **piso da banda definida** — apenas 0,5 pp
   acima do limiar de escalada (15%). A banda existe para absorver erro
   amostral, não para legitimar resultado borderline.
2. Diferença de MAE (Δ = 0,04 pp) **estatisticamente indistinguível
   de zero**: DM-HLN p = 0,64.
3. Encompassing em h=1 é borderline (`AR(1) encompasses DFM-1f`,
   p = 0,10). Não há evidência clara de informação complementar.

### Justificativa para publicação em h=2

1. **Robustez do peso OOS**: w_DFM rolling = 42,4%, praticamente idêntico
   ao 41,1% in-sample. Range estreito [27,3%, 48,5%], dp = 0,028,
   **0 truncamentos** em [0, 1].
2. **Encompassing simétrico**: ambas direções rejeitam H0
   (`λ_DFM->AR1=0,51` p<0,001 e `λ_AR1->DFM=0,49` p<0,001) — DFM e AR(1)
   carregam **informação genuinamente complementar**.
3. **MAE da combinação ≤ MAE AR(1)** em todos os subconjuntos checados,
   ainda que a diferença não seja estatisticamente conclusiva por DM
   (n=58, falta de poder).

### Comunicação dos intervalos

Cobertura empírica de 100% em h=2 (IC95% Wilson [88,3%, 100%]) é
**reportada honestamente como conservadora**, sem shrink empírico. Isso
preserva a garantia formal de Vovk do split conformal (Lei et al. 2018).
A nota técnica do produto explicita que a cobertura empírica está acima
da nominal — viés do lado seguro (intervalos largos demais), não do lado
perigoso (sub-cobertura).
