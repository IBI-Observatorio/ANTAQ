"""
Métricas pontuais e probabilísticas para avaliação de previsões + teste de
Diebold-Mariano com correção HLN para comparação par-a-par de modelos.

Convenção: todas as séries em variação interanual (pp), tipicamente da ordem
de 0,01–0,10. As métricas são reportadas no MESMO eixo (variação) e podem
ser convertidas para pp multiplicando por 100.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


# ─── Métricas pontuais ────────────────────────────────────────────────────────
def mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean(np.abs(np.asarray(y_true) - np.asarray(y_pred))))


def rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.sqrt(np.mean((np.asarray(y_true) - np.asarray(y_pred)) ** 2)))


# ─── Métricas probabilísticas ─────────────────────────────────────────────────
def pinball_loss(y_true: np.ndarray, y_quantile: np.ndarray, q: float) -> float:
    """
    Pinball loss para um nível de quantil q ∈ (0, 1).
    L_q(y, ŷ) = max(q·(y - ŷ), (q - 1)·(y - ŷ))

    Estritamente próprio para o quantil q da distribuição preditiva.
    """
    e = np.asarray(y_true) - np.asarray(y_quantile)
    return float(np.mean(np.maximum(q * e, (q - 1) * e)))


def crps_pinball(y_true: np.ndarray,
                 y_quantiles: dict[float, np.ndarray]) -> float:
    """
    CRPS aproximado pela média de pinball losses sobre níveis de quantil
    uniformemente espaçados.

    Para um conjunto de níveis {τ_1, ..., τ_K} igualmente espaçados em (0, 1),
    CRPS(F, y) ≈ 2 · mean_k L_{τ_k}(y, F^{-1}(τ_k))

    Com 9 níveis (0.1, 0.2, ..., 0.9), a aproximação é razoável; aumentar para
    19 ou 99 níveis melhora monotonicamente em direção ao CRPS exato.
    """
    levels = sorted(y_quantiles.keys())
    losses = [pinball_loss(y_true, y_quantiles[q], q) for q in levels]
    return float(2 * np.mean(losses))


# ─── Diebold-Mariano com correção HLN ─────────────────────────────────────────
def dm_test_hln(e1: np.ndarray, e2: np.ndarray, h: int = 1,
                loss: str = "se") -> tuple[float, float, int]:
    """
    Teste de Diebold-Mariano com correção de Harvey-Leybourne-Newbold (1997).

    H0: E[d_t] = 0 (modelos têm acurácia preditiva igual)
    H1: E[d_t] ≠ 0 (acurácias diferentes)

    onde d_t = L(e1_t) - L(e2_t).

    Args:
        e1, e2 : erros de previsão (modelo 1 e modelo 2), mesma origem/horizonte
        h      : horizonte de previsão (usado para HAC + correção HLN)
        loss   : "se" (squared error) ou "ae" (absolute error)

    Returns:
        (estatística DM-HLN, p-valor bilateral, n)

    Convenção do sinal:
        DM > 0  → modelo 1 tem ERRO MAIOR (modelo 2 vence)
        DM < 0  → modelo 1 tem ERRO MENOR (modelo 1 vence)
    """
    e1, e2 = np.asarray(e1), np.asarray(e2)
    if loss == "se":
        d = e1 ** 2 - e2 ** 2
    elif loss == "ae":
        d = np.abs(e1) - np.abs(e2)
    else:
        raise ValueError(f"loss desconhecida: {loss!r}")

    n = len(d)
    if n < 4:
        return float("nan"), float("nan"), n

    d_mean = float(np.mean(d))

    # HAC variance com truncation lag = h - 1 (Newey-West tipo)
    gamma_0 = float(np.var(d, ddof=0))
    gamma_k = []
    for k in range(1, h):
        if n - k <= 0:
            break
        cov = float(np.mean((d[k:] - d_mean) * (d[:-k] - d_mean)))
        gamma_k.append(cov)
    var_d_long_run = (gamma_0 + 2 * sum(gamma_k)) / n

    if var_d_long_run <= 0 or not np.isfinite(var_d_long_run):
        return float("nan"), float("nan"), n

    dm = d_mean / np.sqrt(var_d_long_run)

    # Correção HLN: ajusta a estatística para amostras pequenas
    hln_factor = np.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)
    dm_hln = float(dm * hln_factor)

    # Distribuição t com n-1 graus de liberdade (HLN)
    p_value = float(2 * (1 - stats.t.cdf(np.abs(dm_hln), df=n - 1)))

    return dm_hln, p_value, n


# ─── Métricas em formato tabular ──────────────────────────────────────────────
def resumir(df_previsoes: pd.DataFrame,
            quantiles_cols: list[str] | None = None) -> pd.DataFrame:
    """
    Recebe DataFrame longo com colunas:
        modelo, h, y_true, q50, [q10, q20, ..., q90]
    Retorna DataFrame com MAE, RMSE, pinball_avg, CRPS por (modelo, h).
    """
    quantiles_cols = quantiles_cols or [c for c in df_previsoes.columns
                                         if c.startswith("q") and c[1:].isdigit()]
    levels = {c: int(c[1:]) / 100 for c in quantiles_cols}

    resumo = []
    for (modelo, h), sub in df_previsoes.groupby(["modelo", "h"]):
        y_true = sub["y_true"].values
        y_pred = sub["q50"].values
        pinball_each = {q: pinball_loss(y_true, sub[c].values, q)
                         for c, q in levels.items()}
        resumo.append({
            "modelo": modelo,
            "h": h,
            "n": len(sub),
            "mae_pp":      mae(y_true, y_pred) * 100,
            "rmse_pp":     rmse(y_true, y_pred) * 100,
            "pinball_avg": float(np.mean(list(pinball_each.values()))) * 100,
            "crps_pp":     crps_pinball(y_true, {q: sub[c].values for c, q in levels.items()}) * 100,
        })
    return (pd.DataFrame(resumo)
              .sort_values(["h", "mae_pp"])
              .reset_index(drop=True))


def encompassing_test_hln(y_true: np.ndarray,
                           forecast_encompasser: np.ndarray,
                           forecast_encompassed: np.ndarray,
                           h: int = 1, alfa: float = 0.05) -> dict:
    """
    Teste de encompassing de Harvey-Leybourne-Newbold (1998).

    H0: o modelo `encompasser` ENCOMPASSES o modelo `encompassed`,
        i.e. as previsões do `encompassed` não agregam informação útil
        às previsões do `encompasser`.

    Regressão (sem ambiguidade):

        e_enc_t = c + λ · (e_enc_t − e_other_t) + u_t

    onde
        e_enc   = y − f_encompasser   (erro do candidato a encompasser)
        e_other = y − f_encompassed   (erro do outro)

    Como  e_enc − e_other = f_encompassed − f_encompasser,  equivalentemente:

        e_enc_t = c + λ · (f_encompassed_t − f_encompasser_t) + u_t

    Inferência com HAC Newey-West, maxlags = max(h, 1).

    Decisão:
        |t| < t_crit  ou  p ≥ α   →  NÃO rejeita H0 → encompasser ENCOMPASSES
                                       o outro (outro é redundante)
        λ̂ > 0  e  p < α            →  REJEITA H0 → encompasser NÃO encompasses
                                       o outro (outro tem info útil)

    Returns:
        {
          "lambda": λ̂, "se_hac", "t_stat", "p_value", "n",
          "rejeita_H0":  bool   (p < α e λ̂ > 0),
          "conclusao":   str    (descrição em palavras),
        }
    """
    import statsmodels.api as sm

    y_true = np.asarray(y_true, dtype=float)
    f_enc   = np.asarray(forecast_encompasser,  dtype=float)
    f_other = np.asarray(forecast_encompassed,  dtype=float)
    e_enc   = y_true - f_enc
    diff    = f_other - f_enc       # = e_enc - e_other

    mask = np.isfinite(e_enc) & np.isfinite(diff)
    if mask.sum() < 5:
        return {"lambda": np.nan, "se_hac": np.nan,
                "t_stat": np.nan, "p_value": np.nan,
                "n": int(mask.sum()),
                "rejeita_H0": False,
                "conclusao": "n insuficiente"}

    Y = e_enc[mask]
    X = sm.add_constant(diff[mask])
    maxlags = max(h, 1)
    res = sm.OLS(Y, X).fit(cov_type="HAC", cov_kwds={"maxlags": maxlags})
    lam = float(res.params[1])
    p   = float(res.pvalues[1])
    rejeita = (p < alfa) and (lam > 0)
    if rejeita:
        conclusao = "REJEITA H0 → encompasser NÃO contém encompassed (outro tem info útil)"
    else:
        conclusao = "NÃO rejeita H0 → encompasser CONTÉM encompassed (outro é redundante)"
    return {
        "lambda":   lam,
        "se_hac":   float(res.bse[1]),
        "t_stat":   float(res.tvalues[1]),
        "p_value":  p,
        "n":        int(mask.sum()),
        "rejeita_H0": bool(rejeita),
        "conclusao":  conclusao,
    }


def combinacao_otima_sum1(y_true: np.ndarray,
                           forecast_1: np.ndarray,
                           forecast_2: np.ndarray,
                           h: int = 1) -> dict:
    """
    Combinação ótima de duas previsões com restrição de soma = 1, sem intercepto
    (Granger-Ramanathan 1984 com restrição convexa).

    Substituição de variável: w_2 = 1 − w_1, combinação c = w_1·f_1 + w_2·f_2.
    Reescrevendo:

        y − f_2 = w_1 · (f_1 − f_2) + u

    Estima w_1 via OLS sem intercepto (a restrição já força isso). HAC SE,
    maxlags = max(h, 1).

    Calcula também MAE/RMSE da combinação resultante e dos componentes,
    para diagnóstico — se w_1 ∈ [0, 1], a combinação é convexa válida.
    Se w_1 < 0 ou w_1 > 1, o ótimo extrapola fora da casca convexa
    (i.e., um dos modelos é tão pior que o ótimo quer peso negativo).

    Returns:
        {"w_1": ŵ_1, "w_2": 1-ŵ_1, "se_hac", "t_stat", "p_value",
         "mae_combinado", "rmse_combinado",
         "mae_f1", "mae_f2", "rmse_f1", "rmse_f2",
         "n": n,
         "convexo": bool}
    """
    import statsmodels.api as sm

    y    = np.asarray(y_true,     dtype=float)
    f1   = np.asarray(forecast_1, dtype=float)
    f2   = np.asarray(forecast_2, dtype=float)
    mask = np.isfinite(y) & np.isfinite(f1) & np.isfinite(f2)
    if mask.sum() < 5:
        return {"w_1": np.nan, "w_2": np.nan, "se_hac": np.nan,
                "t_stat": np.nan, "p_value": np.nan,
                "mae_combinado": np.nan, "rmse_combinado": np.nan,
                "mae_f1": np.nan, "mae_f2": np.nan,
                "rmse_f1": np.nan, "rmse_f2": np.nan,
                "n": int(mask.sum()), "convexo": False}

    y_, f1_, f2_ = y[mask], f1[mask], f2[mask]
    Y = y_ - f2_
    X = (f1_ - f2_).reshape(-1, 1)
    maxlags = max(h, 1)
    res = sm.OLS(Y, X).fit(cov_type="HAC", cov_kwds={"maxlags": maxlags})
    w1 = float(res.params[0])
    w2 = 1.0 - w1
    c  = w1 * f1_ + w2 * f2_
    return {
        "w_1":     w1,
        "w_2":     w2,
        "se_hac":  float(res.bse[0]),
        "t_stat":  float(res.tvalues[0]),
        "p_value": float(res.pvalues[0]),
        "mae_combinado":  float(np.mean(np.abs(y_ - c))),
        "rmse_combinado": float(np.sqrt(np.mean((y_ - c) ** 2))),
        "mae_f1":  float(np.mean(np.abs(y_ - f1_))),
        "mae_f2":  float(np.mean(np.abs(y_ - f2_))),
        "rmse_f1": float(np.sqrt(np.mean((y_ - f1_) ** 2))),
        "rmse_f2": float(np.sqrt(np.mean((y_ - f2_) ** 2))),
        "n":       int(mask.sum()),
        "convexo": bool(0.0 <= w1 <= 1.0),
    }


def dm_pareado(df_previsoes: pd.DataFrame,
               modelo_alvo: str,
               baselines: list[str]) -> pd.DataFrame:
    """
    Para cada (h, baseline), aplica DM-HLN comparando `modelo_alvo` vs baseline.
    Retorna DataFrame com (h, baseline, dm_stat, p_value, n).
    """
    out = []
    for h in sorted(df_previsoes["h"].unique()):
        sub = df_previsoes[df_previsoes["h"] == h]
        alvo = sub[sub["modelo"] == modelo_alvo].set_index("alvo")
        for b in baselines:
            base = sub[sub["modelo"] == b].set_index("alvo")
            comum = alvo.index.intersection(base.index)
            if len(comum) < 4:
                out.append({"h": h, "modelo_alvo": modelo_alvo, "baseline": b,
                            "dm_stat": float("nan"), "p_value": float("nan"),
                            "n": len(comum)})
                continue
            e_alvo = alvo.loc[comum, "y_true"] - alvo.loc[comum, "q50"]
            e_base = base.loc[comum, "y_true"] - base.loc[comum, "q50"]
            dm, p, n = dm_test_hln(e_alvo.values, e_base.values, h=h, loss="se")
            out.append({"h": h, "modelo_alvo": modelo_alvo, "baseline": b,
                        "dm_stat": dm, "p_value": p, "n": n})
    return pd.DataFrame(out)
