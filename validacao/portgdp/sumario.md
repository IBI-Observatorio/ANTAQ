# Validação rolling-origin — PortGDP

- **Janela validada**: 2018-02-01 → 2025-12-01
- **Total de previsões geradas**: 756
- **Modelos comparados**: portgdp_ols (alvo), rw, sazonal_naive, ar1
- **Quantis preditos**: 10%, 20%, 30%, 40%, 50%, 60%, 70%, 80%, 90%
- **Métricas em pp** (variação interanual × 100)

## Métricas por modelo × horizonte

### h = 1

| modelo | n | MAE (pp) | RMSE (pp) | Pinball médio (pp) | CRPS (pp) |
|---|---|---|---|---|---|
| ar1 | 95 | 2.594 | 4.719 | 1.122 | 2.244 |
| rw | 95 | 2.881 | 4.957 | 1.242 | 2.484 |
| portgdp_ols | 95 | 4.474 | 6.970 | 1.941 | 3.881 |
| sazonal_naive | 95 | 6.856 | 11.424 | 2.902 | 5.804 |

### h = 2

| modelo | n | MAE (pp) | RMSE (pp) | Pinball médio (pp) | CRPS (pp) |
|---|---|---|---|---|---|
| ar1 | 94 | 3.676 | 6.411 | 1.603 | 3.206 |
| rw | 94 | 4.130 | 7.148 | 1.809 | 3.619 |
| portgdp_ols | 94 | 4.660 | 7.305 | 2.040 | 4.080 |
| sazonal_naive | 94 | 6.922 | 11.522 | 2.952 | 5.904 |

## Diebold-Mariano com correção HLN — portgdp_ols vs baselines

Convenção: `dm_stat < 0` indica que portgdp_ols tem erro quadrático
**menor** que o baseline. p-valor bilateral.

| h | baseline | n | DM stat | p-valor | sig. |
|---|---|---|---|---|---|
| 1 | rw | 95 | 2.893 | 0.005 | *** |
| 1 | sazonal_naive | 95 | -2.448 | 0.016 | ** |
| 1 | ar1 | 95 | 3.336 | 0.001 | *** |
| 2 | rw | 94 | 0.190 | 0.849 | ns |
| 2 | sazonal_naive | 94 | -1.626 | 0.107 | ns |
| 2 | ar1 | 94 | 1.275 | 0.205 | ns |

> sig.: `***` p<0,01 · `**` p<0,05 · `*` p<0,10 · `ns` não signif.
