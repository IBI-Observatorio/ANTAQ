# Sumário executivo — Spike DFM PortGDP v2

## → **Linha D**

> Comovimento estrutural com componente preditivo marginal. Encompassing rejeita que AR(1) encompasses DFM (ARDL agrega sinal além da autocorrelação), ainda que DM e GR não favoreçam.

## Detalhes

```json
[
  {
    "h": 2,
    "encompasser": "ar1",
    "encompassed": "dfm_1f",
    "lambda": 0.4890295302141022,
    "se_hac": 0.1169228405745057,
    "t_stat": 4.182497857657523,
    "p_value": 2.8832373544464323e-05,
    "n": 94,
    "rejeita_H0": true
  }
]
```

## Métricas walk-forward (todos os modelos)

| modelo | h | n | mae_pp | rmse_pp | pinball_avg | crps_pp |
|---|---|---|---|---|---|---|
| ar1 | 1 | 95 | 2.594 | 4.719 | 1.122 | 2.244 |
| rw | 1 | 95 | 2.881 | 4.957 | 1.242 | 2.484 |
| ardl | 1 | 95 | 3.355 | 5.273 | 1.439 | 2.878 |
| dfm_1f | 1 | 94 | 4.067 | 6.754 | 1.734 | 3.469 |
| dfm_2f | 1 | 94 | 5.173 | 7.631 | 2.178 | 4.357 |
| sazonal_naive | 1 | 95 | 6.856 | 11.424 | 2.902 | 5.804 |
| ar1 | 2 | 94 | 3.676 | 6.411 | 1.603 | 3.206 |
| dfm_1f | 2 | 94 | 4.069 | 6.737 | 1.882 | 3.764 |
| rw | 2 | 94 | 4.130 | 7.148 | 1.809 | 3.619 |
| ardl | 2 | 94 | 4.488 | 7.123 | 1.948 | 3.897 |
| dfm_2f | 2 | 94 | 5.351 | 8.094 | 2.279 | 4.557 |
| sazonal_naive | 2 | 94 | 6.922 | 11.522 | 2.952 | 5.904 |

## DM-HLN — DFM vs AR(1), DFM vs ARDL

Convenção: `dm_stat < 0` indica que `modelo_alvo` tem erro **menor** que `baseline`.

| h | modelo_alvo | baseline | dm_stat | p_value | n |
|---|---|---|---|---|---|
| 1 | dfm_1f | ar1 | 2.4171 | 0.0176 | 94 |
| 1 | dfm_1f | ardl | 1.7928 | 0.0763 | 94 |
| 2 | dfm_1f | ar1 | 0.6826 | 0.4966 | 94 |
| 2 | dfm_1f | ardl | -0.4244 | 0.6723 | 94 |
| 1 | dfm_2f | ar1 | 4.0450 | 0.0001 | 94 |
| 1 | dfm_2f | ardl | 4.1260 | 0.0001 | 94 |
| 2 | dfm_2f | ar1 | 1.8227 | 0.0716 | 94 |
| 2 | dfm_2f | ardl | 2.1883 | 0.0312 | 94 |

## Encompassing test (HLN 1998)

H0 testada: `encompasser` ENCOMPASSES `encompassed`. Rejeita H0 ⟺ `encompassed` agrega informação útil.

| h | encompasser | encompassed | lambda | se_hac | t_stat | p_value | n | rejeita_H0 |
|---|---|---|---|---|---|---|---|---|
| 1 | dfm_1f | ar1 | 0.8218 | 0.1097 | 7.4917 | 0.0000 | 94 | True |
| 1 | ar1 | dfm_1f | 0.1782 | 0.1097 | 1.6240 | 0.1044 | 94 | False |
| 1 | dfm_2f | ar1 | 0.9692 | 0.0850 | 11.4008 | 0.0000 | 94 | True |
| 1 | ar1 | dfm_2f | 0.0308 | 0.0850 | 0.3622 | 0.7172 | 94 | False |
| 2 | dfm_1f | ar1 | 0.5110 | 0.1169 | 4.3702 | 0.0000 | 94 | True |
| 2 | ar1 | dfm_1f | 0.4890 | 0.1169 | 4.1825 | 0.0000 | 94 | True |
| 2 | dfm_2f | ar1 | 0.8945 | 0.1561 | 5.7311 | 0.0000 | 94 | True |
| 2 | ar1 | dfm_2f | 0.1055 | 0.1561 | 0.6756 | 0.4993 | 94 | False |

## Granger-Ramanathan restrito (soma=1)

| w_1 | w_2 | se_hac | t_stat | p_value | mae_combinado | rmse_combinado | mae_f1 | mae_f2 | rmse_f1 | rmse_f2 | n | convexo | h | f1 | f2 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.1481 | 0.8519 | 0.1061 | 1.3957 | 0.1628 | 0.0252 | 0.0466 | 0.0407 | 0.0260 | 0.0675 | 0.0474 | 94 | True | 1 | dfm_1f | ar1 |
| 0.0331 | 0.9669 | 0.0830 | 0.3985 | 0.6902 | 0.0259 | 0.0474 | 0.0517 | 0.0260 | 0.0763 | 0.0474 | 94 | True | 1 | dfm_2f | ar1 |
| 0.4113 | 0.5887 | 0.1256 | 3.2760 | 0.0011 | 0.0347 | 0.0608 | 0.0407 | 0.0368 | 0.0674 | 0.0641 | 94 | True | 2 | dfm_1f | ar1 |
| 0.1117 | 0.8883 | 0.1530 | 0.7305 | 0.4651 | 0.0370 | 0.0638 | 0.0535 | 0.0368 | 0.0809 | 0.0641 | 94 | True | 2 | dfm_2f | ar1 |
