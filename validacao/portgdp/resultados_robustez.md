# Resultados — Bateria de robustez ARDL (item 2)

**Especificação aplicada:** AR(p=2), lag_x=2, HAC_lag=12
**Tempo total de execução:** 2.3s

## Decisão aplicada (regra pré-registrada)

### → **Linha E**

> Indicador de comovimento contemporâneo (lag estrutural −2). Descritivo, não preditivo. Recua do claim original de "antecedente do PIB industrial".

**Gatilhos ativados:**
- ARDL bate AR(1) em h=1: `False`
- ARDL bate AR(1) em h=2: `False`
- Ensemble bate AR(1) em h=1: `False`
- Ensemble bate AR(1) em h=2: `False`
- Encompassing favorece ARDL: `False`

## 1. Coeficientes ARDL full-sample (HAC Newey-West, lag 12)

| termo | coef | se_hac | t_stat | p_value |
|---|---|---|---|---|
| const | -0.0024 | 0.0021 | -1.1275 | 0.2595 |
| y_lag1 | 0.8562 | 0.1360 | 6.2977 | 0.0000 |
| y_lag2 | -0.1577 | 0.1395 | -1.1309 | 0.2581 |
| x_lag2 | 0.0693 | 0.0200 | 3.4632 | 0.0005 |
| d_covid | 0.0062 | 0.0163 | 0.3812 | 0.7030 |
| d_x_lag2 | -0.0944 | 0.0271 | -3.4849 | 0.0005 |

## 2. Diagnósticos de resíduo

| teste | stat | p_value |
|---|---|---|
| Ljung-Box (lag 12) | 31.2540 | 0.0018 |
| Ljung-Box (lag 24) | 59.2420 | 0.0001 |
| Breusch-Godfrey (lag 12) | 29.5452 | 0.0033 |
| Jarque-Bera | 1936.5152 | 0.0000 |
| ARCH-LM (lag 12) | 23.4826 | 0.0239 |

## 3. ARDL sem COVID

Δ relativo de β (full → sem_covid): **23.6%**

| versao | n | beta_x_lag2 | p_value |
|---|---|---|---|
| full | 130.0000 | 0.0693 | 0.0005 |
| sem_covid | 108.0000 | 0.0530 | 0.0563 |
| delta_rel | nan | 0.2356 | nan |

## 4. Métricas walk-forward

| modelo | h | n | mae_pp | rmse_pp | pinball_avg | crps_pp |
|---|---|---|---|---|---|---|
| ar1 | 1 | 95 | 2.594 | 4.719 | 1.122 | 2.244 |
| ens_media | 1 | 95 | 2.891 | 4.857 | 1.230 | 2.461 |
| ens_mediana | 1 | 95 | 2.891 | 4.857 | 1.230 | 2.461 |
| ardl | 1 | 95 | 3.355 | 5.273 | 1.439 | 2.878 |
| ar1 | 2 | 94 | 3.676 | 6.411 | 1.603 | 3.206 |
| ens_media | 2 | 94 | 3.977 | 6.583 | 1.724 | 3.449 |
| ens_mediana | 2 | 94 | 3.977 | 6.583 | 1.724 | 3.449 |
| ardl | 2 | 94 | 4.488 | 7.123 | 1.948 | 3.897 |

## 5. DM-HLN

| h | modelo_alvo | baseline | dm_stat | p_value | n |
|---|---|---|---|---|---|
| 1 | ardl | ar1 | 2.0626 | 0.0419 | 95 |
| 2 | ardl | ar1 | 1.0775 | 0.2841 | 94 |
| 1 | ens_mediana | ar1 | 1.1226 | 0.2645 | 95 |
| 1 | ens_mediana | ardl | -2.7010 | 0.0082 | 95 |
| 2 | ens_mediana | ar1 | 0.6158 | 0.5396 | 94 |
| 2 | ens_mediana | ardl | -1.3775 | 0.1717 | 94 |
| 1 | ens_media | ar1 | 1.1226 | 0.2645 | 95 |
| 1 | ens_media | ardl | -2.7010 | 0.0082 | 95 |
| 2 | ens_media | ar1 | 0.6158 | 0.5396 | 94 |
| 2 | ens_media | ardl | -1.3775 | 0.1717 | 94 |

## 6. Encompassing test (HLN 1998)

Convenção: H0 testada é "`encompasser` ENCOMPASSES `encompassed`".
Rejeita H0 (`rejeita_H0=True`) ⟺ `encompassed` agrega informação útil.

| h | encompasser | encompassed | lambda | se_hac | t_stat | p_value | n | rejeita_H0 | conclusao |
|---|---|---|---|---|---|---|---|---|---|
| 1 | ardl | ar1 | 0.9830 | 0.1907 | 5.1538 | 0.0000 | 95 | True | REJEITA H0 → encompasser NÃO contém encompassed (outro tem info útil) |
| 1 | ar1 | ardl | 0.0170 | 0.1907 | 0.0892 | 0.9289 | 95 | False | NÃO rejeita H0 → encompasser CONTÉM encompassed (outro é redundante) |
| 2 | ardl | ar1 | 0.9810 | 0.2558 | 3.8351 | 0.0001 | 94 | True | REJEITA H0 → encompasser NÃO contém encompassed (outro tem info útil) |
| 2 | ar1 | ardl | 0.0190 | 0.2558 | 0.0742 | 0.9408 | 94 | False | NÃO rejeita H0 → encompasser CONTÉM encompassed (outro é redundante) |

## 6b. Combinação ótima OOS (soma = 1)

Granger-Ramanathan restrito: `y = w_1·f_1 + w_2·f_2 + u`,
`w_1 + w_2 = 1`, sem intercepto. SE com HAC.
Convexo (`w_1 ∈ [0,1]`) indica combinação válida na casca convexa.

| w_1 | w_2 | se_hac | t_stat | p_value | mae_combinado | rmse_combinado | mae_f1 | mae_f2 | rmse_f1 | rmse_f2 | n | convexo | h | f1 | f2 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.0223 | 0.9777 | 0.1966 | 0.1136 | 0.9096 | 0.0260 | 0.0472 | 0.0336 | 0.0259 | 0.0527 | 0.0472 | 95 | True | 1 | ardl | ar1 |
| 0.0343 | 0.9657 | 0.2659 | 0.1289 | 0.8974 | 0.0369 | 0.0641 | 0.0449 | 0.0368 | 0.0712 | 0.0641 | 94 | True | 2 | ardl | ar1 |

## 7. Robustez log-diff mensal

Métricas walk-forward na escala var12m (após agregação):

| modelo | h | n | mae_pp | rmse_pp | pinball_avg | crps_pp |
|---|---|---|---|---|---|---|
| ar1_logdiff | 1 | 106 | 1.702 | 3.637 | 0.751 | 1.503 |
| ardl_logdiff | 1 | 106 | 1.911 | 4.207 | 0.840 | 1.681 |
| ar1_logdiff | 2 | 105 | 2.242 | 4.877 | 1.042 | 2.084 |
| ardl_logdiff | 2 | 105 | 2.489 | 5.588 | 1.170 | 2.340 |

DM ARDL log-diff vs AR(1) log-diff:

| h | modelo_alvo | baseline | dm_stat | p_value | n |
|---|---|---|---|---|---|
| 1 | ardl_logdiff | ar1_logdiff | 1.0213 | 0.3094 | 106 |
| 2 | ardl_logdiff | ar1_logdiff | 0.8335 | 0.4065 | 105 |
