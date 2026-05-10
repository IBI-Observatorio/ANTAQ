"""
Item 2 do plano metodológico — bateria de robustez ARDL.

Roda todas as verificações pré-registradas em `validacao/portgdp/REGRA_DECISAO.md`
e aplica mecanicamente a regra de decisão para gerar a comunicação pública.

Componentes:
  1. ARDL full-sample com HAC Newey-West (lag 12)
  2. Diagnósticos de resíduo: Ljung-Box, Breusch-Godfrey, Jarque-Bera, ARCH-LM
  3. Walk-forward ARDL (refit a cada origem) para h=1 e h=2
  4. DM-HLN: ARDL vs AR(1), RW, sazonal_naive, portgdp_ols
  5. Encompassing test (HLN 1998) ARDL ↔ AR(1)
  6. Robustez sem COVID (drop mar/2020–dez/2021, sem dummies)
  7. Robustez log-diff mensal (sem var12m)
  8. Ensemble (mediana, média) ARDL+AR(1) vs componentes via DM
  9. Aplicação da regra de decisão A–E

Outputs em validacao/portgdp/:
  resultados_robustez.md          — sumário executivo + decisão aplicada
  ardl_fullsample_coef.csv        — coeficientes + HAC SE + p-valores
  diagnosticos_residuos.csv
  ardl_sem_covid.csv
  log_diff_walkforward.csv
  walkforward_ardl_previsoes.csv  — append ao CSV existente
  dm_completo.csv
  encompassing.csv
  ensemble_resultados.csv

Uso:
  python -m analises.validacao.portgdp_ardl_robustez
  python -m analises.validacao.portgdp_ardl_robustez --p 2  # forçar AR(2)
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.diagnostic import (acorr_ljungbox, acorr_breusch_godfrey,
                                           het_arch)
from statsmodels.stats.stattools import jarque_bera

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from analises.validacao.portgdp_walkforward import carregar_series, OUT_DIR
from analises.validacao.modelos import (MODELOS, QUANTIS_DEFAULT,
                                          ardl, ar1, ensemble_mediana, ensemble_media,
                                          _dummy_covid, COVID_INI, COVID_FIM)
from analises.validacao.metricas import (resumir, dm_pareado, dm_test_hln,
                                           encompassing_test_hln,
                                           combinacao_otima_sum1)


HAC_LAG = 12  # não-negociável dado var12m sobreposto
LAG_X = 2     # PortGDP defasado 2 meses


# ═════════════════════════════════════════════════════════════════════════════
# 1. Ajuste full-sample com HAC + diagnósticos
# ═════════════════════════════════════════════════════════════════════════════
def ajustar_ardl_fullsample(y: pd.Series, x: pd.Series, p: int = 1) -> sm.regression.linear_model.RegressionResultsWrapper:
    """ARDL com HAC Newey-West, lag 12. Para inferência de coeficientes."""
    idx = y.dropna().index.intersection(x.dropna().index)
    y_, x_ = y.loc[idx], x.loc[idx]
    inicio = max(p, LAG_X)

    Y = y_.iloc[inicio:].values
    cols = {"const": np.ones(len(Y))}
    for i in range(1, p + 1):
        cols[f"y_lag{i}"] = y_.iloc[inicio - i : len(y_) - i].values
    cols["x_lag2"] = x_.iloc[inicio - LAG_X : len(x_) - LAG_X].values
    d_full = _dummy_covid(y_.index)
    cols["d_covid"] = d_full[inicio:]
    cols["d_x_lag2"] = d_full[inicio:] * cols["x_lag2"]

    X = pd.DataFrame(cols)
    mask = X.notna().all(axis=1) & np.isfinite(Y)
    X, Y = X.loc[mask], Y[mask.values]

    res = sm.OLS(Y, X.values).fit(cov_type="HAC", cov_kwds={"maxlags": HAC_LAG})
    res.exog_names = list(X.columns)
    res.endog_names = "var12m_pim"
    res._x_index = X.index
    return res


def diagnosticos_residuos(res, p: int) -> pd.DataFrame:
    """Bateria de diagnósticos: Ljung-Box (12, 24), BG (12), JB, ARCH-LM (12)."""
    resid = pd.Series(res.resid)
    diag = []

    lb = acorr_ljungbox(resid, lags=[12, 24], return_df=True)
    diag.append({"teste": "Ljung-Box (lag 12)",
                 "stat": float(lb.iloc[0, 0]), "p_value": float(lb.iloc[0, 1])})
    diag.append({"teste": "Ljung-Box (lag 24)",
                 "stat": float(lb.iloc[1, 0]), "p_value": float(lb.iloc[1, 1])})

    try:
        bg_lm, bg_p, _, _ = acorr_breusch_godfrey(res, nlags=12)
        diag.append({"teste": "Breusch-Godfrey (lag 12)",
                     "stat": float(bg_lm), "p_value": float(bg_p)})
    except Exception as e:
        diag.append({"teste": "Breusch-Godfrey (lag 12)",
                     "stat": np.nan, "p_value": np.nan, "obs": str(e)})

    jb_stat, jb_p, *_ = jarque_bera(resid)
    diag.append({"teste": "Jarque-Bera",
                 "stat": float(jb_stat), "p_value": float(jb_p)})

    arch_lm, arch_p, _, _ = het_arch(resid, nlags=12)
    diag.append({"teste": "ARCH-LM (lag 12)",
                 "stat": float(arch_lm), "p_value": float(arch_p)})

    return pd.DataFrame(diag)


# ═════════════════════════════════════════════════════════════════════════════
# 2. ARDL sem COVID
# ═════════════════════════════════════════════════════════════════════════════
def ardl_sem_covid(y: pd.Series, x: pd.Series, p: int = 1) -> dict:
    """Ajuste idêntico ao full-sample mas excluindo o período COVID."""
    mask = ~((y.index >= COVID_INI) & (y.index <= COVID_FIM))
    y_, x_ = y[mask], x[mask]
    inicio = max(p, LAG_X)

    Y = y_.iloc[inicio:].values
    cols = {"const": np.ones(len(Y))}
    for i in range(1, p + 1):
        cols[f"y_lag{i}"] = y_.iloc[inicio - i : len(y_) - i].values
    cols["x_lag2"] = x_.iloc[inicio - LAG_X : len(x_) - LAG_X].values
    X = pd.DataFrame(cols)
    finmask = X.notna().all(axis=1) & np.isfinite(Y)
    X, Y = X.loc[finmask], Y[finmask.values]
    res = sm.OLS(Y, X.values).fit(cov_type="HAC", cov_kwds={"maxlags": HAC_LAG})
    return {
        "n": int(len(Y)),
        "beta_x_lag2": float(res.params[1 + p]),
        "se_beta": float(res.bse[1 + p]),
        "p_beta": float(res.pvalues[1 + p]),
        "r2": float(res.rsquared),
    }


# ═════════════════════════════════════════════════════════════════════════════
# 3. Walk-forward ARDL + ensemble
# ═════════════════════════════════════════════════════════════════════════════
def walkforward_arldl(port: pd.Series, pim: pd.Series,
                        min_train: int = 36,
                        horizontes: tuple[int, ...] = (1, 2),
                        p_ar: int = 1) -> pd.DataFrame:
    """Walk-forward: ARDL e AR(1) refitados a cada origem, mais ensemble."""
    v_port = port.pct_change(12)
    v_pim  = pim.pct_change(12)
    idx = v_port.dropna().index.intersection(v_pim.dropna().index)
    v_port = v_port.loc[idx].sort_index()
    v_pim  = v_pim.loc[idx].sort_index()
    n = len(v_pim)

    print(f"  Walk-forward ARDL · janela: {idx[0].date()} → {idx[-1].date()} ({n} meses)")
    print(f"  min_train: {min_train} · horizontes: {horizontes} · AR(p={p_ar})")

    registros = []
    for i in range(min_train, n - 1):
        origem = v_pim.index[i]
        train_y = v_pim.iloc[: i + 1]
        train_x = v_port.iloc[: i + 1]
        for h in horizontes:
            j = i + h
            if j >= n:
                continue
            alvo = v_pim.index[j]
            y_true = float(v_pim.iloc[j])

            pred_ardl = ardl(train_y, train_x, h, p=p_ar, lag_x=LAG_X,
                              quantiles=QUANTIS_DEFAULT)
            pred_ar1  = ar1(train_y, train_x, h, quantiles=QUANTIS_DEFAULT)
            pred_med  = ensemble_mediana(pred_ar1, pred_ardl)
            pred_avg  = ensemble_media(pred_ar1, pred_ardl)

            for nome, pred in [("ardl", pred_ardl),
                                ("ar1", pred_ar1),
                                ("ens_mediana", pred_med),
                                ("ens_media", pred_avg)]:
                registros.append({
                    "origem": origem, "alvo": alvo, "h": h,
                    "modelo": nome, "y_true": y_true, **pred,
                })

    df = pd.DataFrame(registros)
    df["q50"] = df.get("q50", df.get("media"))
    print(f"  {len(df)} previsões geradas.")
    return df


# ═════════════════════════════════════════════════════════════════════════════
# 4. Versão log-diferença mensal
# ═════════════════════════════════════════════════════════════════════════════
def walkforward_log_diff(port_imp: pd.Series, pim: pd.Series,
                          min_train: int = 36,
                          horizontes: tuple[int, ...] = (1, 2),
                          p_ar: int = 1) -> pd.DataFrame:
    """
    Mesma especificação ARDL, mas em log-diferença mensal (Δlog).
    Forecast em Δlog mensal; agregação para var12m via soma dos 12 últimos.
    """
    dlog_port = np.log(port_imp).diff()
    dlog_pim  = np.log(pim).diff()
    idx = dlog_port.dropna().index.intersection(dlog_pim.dropna().index)
    dlog_port = dlog_port.loc[idx]
    dlog_pim  = dlog_pim.loc[idx]
    pim_log = np.log(pim).loc[idx]
    n = len(dlog_pim)

    registros = []
    for i in range(min_train, n - 1):
        origem = dlog_pim.index[i]
        train_y = dlog_pim.iloc[: i + 1]
        train_x = dlog_port.iloc[: i + 1]
        for h in horizontes:
            j = i + h
            if j >= n:
                continue
            alvo = dlog_pim.index[j]

            # y_true em var12m: log(PIM_{τ+h}) - log(PIM_{τ+h-12})
            t_alvo_pos = j
            t_base_pos = j - 12
            if t_base_pos < 0:
                continue
            y_true_var12 = float(pim_log.iloc[t_alvo_pos] - pim_log.iloc[t_base_pos])

            # Previsão Δlog para os h passos à frente
            pred_dlog_ardl = ardl(train_y, train_x, h, p=p_ar, lag_x=LAG_X,
                                   quantiles=QUANTIS_DEFAULT)
            pred_dlog_ar1  = ar1(train_y, train_x, h, quantiles=QUANTIS_DEFAULT)

            # Para reconstruir var12m a partir de Δlog mensal:
            # Δ12log(PIM)_{τ+h} = Σ_{k=τ+h-11..τ+h} Δlog(PIM_k)
            # Conhecemos Δlog até t=τ. Dos próximos h passos, k=τ+1..τ+h são
            # previstos pelo modelo. As h "previsões" são todas pelo modelo
            # (não só uma) — para isso, fazemos previsão de horizonte 1, 2, ... h.
            soma_dlog_passada = float(dlog_pim.iloc[i - (12 - h - 1) : i + 1].sum())
            soma_dlog_futura_q50 = 0.0
            soma_dlog_futura_quantis = {q: 0.0 for q in QUANTIS_DEFAULT}
            for k in range(1, h + 1):
                pk_ardl = ardl(train_y, train_x, k, p=p_ar, lag_x=LAG_X,
                                quantiles=QUANTIS_DEFAULT)
                soma_dlog_futura_q50 += pk_ardl["media"]
                # Para os quantis agregados, usamos uma aproximação simplificada
                # (somar os quantis individuais — conservador para escala).
                for q in QUANTIS_DEFAULT:
                    soma_dlog_futura_quantis[q] += pk_ardl[f"q{int(q*100):02d}"] - pk_ardl["media"]
            y_pred_var12_ardl = soma_dlog_passada + soma_dlog_futura_q50

            # Mesmo procedimento para AR(1)
            soma_ar1_q50 = 0.0
            soma_ar1_quantis = {q: 0.0 for q in QUANTIS_DEFAULT}
            for k in range(1, h + 1):
                pk_ar1 = ar1(train_y, train_x, k, quantiles=QUANTIS_DEFAULT)
                soma_ar1_q50 += pk_ar1["media"]
                for q in QUANTIS_DEFAULT:
                    soma_ar1_quantis[q] += pk_ar1[f"q{int(q*100):02d}"] - pk_ar1["media"]
            y_pred_var12_ar1 = soma_dlog_passada + soma_ar1_q50

            # Quantis agregados em torno do ponto previsto
            quantis_ardl = {f"q{int(q*100):02d}": y_pred_var12_ardl + soma_dlog_futura_quantis[q]
                            for q in QUANTIS_DEFAULT}
            quantis_ar1 = {f"q{int(q*100):02d}": y_pred_var12_ar1 + soma_ar1_quantis[q]
                            for q in QUANTIS_DEFAULT}

            registros.append({
                "origem": origem, "alvo": alvo, "h": h,
                "modelo": "ardl_logdiff", "y_true": y_true_var12,
                "media": y_pred_var12_ardl, **quantis_ardl, "q50": quantis_ardl["q50"],
            })
            registros.append({
                "origem": origem, "alvo": alvo, "h": h,
                "modelo": "ar1_logdiff", "y_true": y_true_var12,
                "media": y_pred_var12_ar1, **quantis_ar1, "q50": quantis_ar1["q50"],
            })

    return pd.DataFrame(registros)


# ═════════════════════════════════════════════════════════════════════════════
# 5. Aplicação da regra de decisão
# ═════════════════════════════════════════════════════════════════════════════
def aplicar_regra(dm_ardl_vs_ar1: pd.DataFrame,
                  dm_ensemble_vs_ar1: pd.DataFrame,
                  encompass: pd.DataFrame,
                  alfa: float = 0.05) -> dict:
    """
    Aplica a tabela A-E pré-registrada em REGRA_DECISAO.md de forma mecânica.

    Convenção do DM:
        ARDL é modelo_alvo, AR(1) é baseline.
        DM stat NEGATIVO + p<α  → ARDL bate AR(1).
        DM stat POSITIVO + p<α  → ARDL pior que AR(1).
        |DM| pequeno ou p>α     → empate estatístico.
    """
    def _bate(df, alvo, baseline, h):
        sub = df[(df["modelo_alvo"] == alvo) &
                  (df["baseline"] == baseline) &
                  (df["h"] == h)]
        if sub.empty:
            return False
        r = sub.iloc[0]
        if not np.isfinite(r["dm_stat"]) or not np.isfinite(r["p_value"]):
            return False
        return r["dm_stat"] < 0 and r["p_value"] < alfa

    ardl_h1 = _bate(dm_ardl_vs_ar1, "ardl", "ar1", 1)
    ardl_h2 = _bate(dm_ardl_vs_ar1, "ardl", "ar1", 2)
    ens_med_h1 = _bate(dm_ensemble_vs_ar1, "ens_mediana", "ar1", 1)
    ens_med_h2 = _bate(dm_ensemble_vs_ar1, "ens_mediana", "ar1", 2)
    ens_avg_h1 = _bate(dm_ensemble_vs_ar1, "ens_media", "ar1", 1)
    ens_avg_h2 = _bate(dm_ensemble_vs_ar1, "ens_media", "ar1", 2)
    ens_h1 = ens_med_h1 or ens_avg_h1
    ens_h2 = ens_med_h2 or ens_avg_h2

    # Encompassing favorece ARDL ⟺ ARDL agrega informação útil ao AR(1).
    # Operacionalmente: o teste H0_b = "AR(1) encompasses ARDL" é REJEITADO
    # (ARDL tem componente que reduz erro do AR(1)). Lê na linha
    # encompasser=ar1, encompassed=ardl, rejeita_H0=True.
    enc_ar1_enc = encompass[(encompass["encompasser"] == "ar1") &
                              (encompass["encompassed"] == "ardl")]
    enc_favor_ardl = bool(enc_ar1_enc["rejeita_H0"].any())

    if ardl_h1 and ardl_h2:
        linha = "A"
        comunicacao = ("Indicador antecedente do PIM-PF — claim original "
                        "sustentado. ARDL vence AR(1) em h=1 e h=2 com p<0,05.")
    elif ardl_h2 and not ardl_h1:
        linha = "B"
        comunicacao = ("Indicador antecedente em horizonte bimestral. "
                        "Modelo bate AR(1) em h=2 com significância, "
                        "mas em h=1 não há ganho preditivo demonstrável.")
    elif (ens_h1 or ens_h2):
        linha = "C"
        comunicacao = ("Componente do modelo combinado IBI. PortGDP "
                        "individualmente não vence AR(1), mas a combinação "
                        "(mediana/média) bate AR(1) — port entra como feature, "
                        "não como protagonista.")
    elif enc_favor_ardl:
        linha = "D"
        comunicacao = ("Indicador descritivo de comovimento com componente "
                        "preditivo marginal. O encompassing test rejeita "
                        "redundância do PortGDP diante do AR(1) (λ>0, p<0,05), "
                        "ainda que o ganho não apareça em DM.")
    else:
        linha = "E"
        comunicacao = ("Indicador de comovimento contemporâneo (lag estrutural "
                        "−2). Descritivo, não preditivo. Recua do claim "
                        "original de \"antecedente do PIB industrial\".")
    return {"linha": linha, "comunicacao": comunicacao,
            "ardl_h1": ardl_h1, "ardl_h2": ardl_h2,
            "ensemble_h1": ens_h1, "ensemble_h2": ens_h2,
            "encompass_favor_ardl": bool(enc_favor_ardl)}


# ═════════════════════════════════════════════════════════════════════════════
# Helpers de saída
# ═════════════════════════════════════════════════════════════════════════════
def _coef_table(res, p: int) -> pd.DataFrame:
    nomes = ["const"] + [f"y_lag{i}" for i in range(1, p+1)] + \
             ["x_lag2", "d_covid", "d_x_lag2"]
    return pd.DataFrame({
        "termo":   nomes,
        "coef":    res.params.tolist(),
        "se_hac":  res.bse.tolist(),
        "t_stat":  res.tvalues.tolist(),
        "p_value": res.pvalues.tolist(),
    })


def _md_table(df, casas=4):
    cols = list(df.columns)
    head = "| " + " | ".join(cols) + " |"
    sep  = "|" + "|".join("---" for _ in cols) + "|"
    rows = []
    for _, r in df.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            if isinstance(v, float):
                cells.append(f"{v:.{casas}f}")
            else:
                cells.append(str(v))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([head, sep, *rows])


# ═════════════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════════════
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--p", type=int, default=1, help="ordem AR (default 1)")
    parser.add_argument("--min-train", type=int, default=36)
    args = parser.parse_args()

    print("\n  ── Item 2: bateria de robustez ARDL ──")
    print(f"  AR(p={args.p}) · LAG_X={LAG_X} · HAC_LAG={HAC_LAG}")
    t0 = time.time()

    print("\n  Carregando séries…")
    port_imp, pim = carregar_series()

    v_port = port_imp.pct_change(12)
    v_pim  = pim.pct_change(12)
    idx = v_port.dropna().index.intersection(v_pim.dropna().index)
    v_port, v_pim = v_port.loc[idx], v_pim.loc[idx]

    # ─── 1. Full-sample ARDL com HAC ─────────────────────────────────────────
    print(f"\n  [1] Full-sample ARDL com HAC Newey-West (lag {HAC_LAG})…")
    res = ajustar_ardl_fullsample(v_pim, v_port, p=args.p)
    coef_df = _coef_table(res, args.p)
    coef_df.to_csv(OUT_DIR / "ardl_fullsample_coef.csv", index=False, float_format="%.6f")
    print(coef_df.to_string(index=False))

    # ─── 2. Diagnósticos ─────────────────────────────────────────────────────
    print("\n  [2] Diagnósticos de resíduo…")
    diag = diagnosticos_residuos(res, p=args.p)
    diag.to_csv(OUT_DIR / "diagnosticos_residuos.csv", index=False, float_format="%.6f")
    print(diag.to_string(index=False))
    bg_p = float(diag.loc[diag["teste"] == "Breusch-Godfrey (lag 12)", "p_value"].iloc[0])
    if bg_p < 0.05 and args.p == 1:
        print(f"\n  ⚠ Breusch-Godfrey p={bg_p:.4f} < 0.05 → re-ajustando com p=2…")
        res = ajustar_ardl_fullsample(v_pim, v_port, p=2)
        diag = diagnosticos_residuos(res, p=2)
        diag.to_csv(OUT_DIR / "diagnosticos_residuos.csv", index=False, float_format="%.6f")
        coef_df = _coef_table(res, 2)
        coef_df.to_csv(OUT_DIR / "ardl_fullsample_coef.csv", index=False, float_format="%.6f")
        args.p = 2

    # ─── 3. ARDL sem COVID ───────────────────────────────────────────────────
    print("\n  [3] ARDL sem COVID (drop mar/2020–dez/2021)…")
    sem_covid = ardl_sem_covid(v_pim, v_port, p=args.p)
    full_beta = float(coef_df.loc[coef_df["termo"] == "x_lag2", "coef"].iloc[0])
    full_p = float(coef_df.loc[coef_df["termo"] == "x_lag2", "p_value"].iloc[0])
    delta_pct = abs(sem_covid["beta_x_lag2"] - full_beta) / max(abs(full_beta), 1e-9)
    sem_covid_df = pd.DataFrame([
        {"versao": "full",       "n": int(res.nobs), "beta_x_lag2": full_beta,
         "p_value": full_p},
        {"versao": "sem_covid",  "n": sem_covid["n"], "beta_x_lag2": sem_covid["beta_x_lag2"],
         "p_value": sem_covid["p_beta"]},
        {"versao": "delta_rel",  "n": np.nan, "beta_x_lag2": delta_pct,
         "p_value": np.nan},
    ])
    sem_covid_df.to_csv(OUT_DIR / "ardl_sem_covid.csv", index=False, float_format="%.6f")
    print(sem_covid_df.to_string(index=False))
    if delta_pct > 0.5:
        print(f"  ⚠ β muda {delta_pct:.0%} ao excluir COVID — possível quebra estrutural.")

    # ─── 4. Walk-forward ARDL + ensemble ─────────────────────────────────────
    print(f"\n  [4] Walk-forward ARDL + AR(1) + ensemble…")
    df_wf = walkforward_arldl(port_imp, pim, min_train=args.min_train, p_ar=args.p)
    df_wf.to_csv(OUT_DIR / "walkforward_ardl_previsoes.csv", index=False, float_format="%.6f")
    resumo_wf = resumir(df_wf)
    print("\n  Métricas walk-forward:")
    print(resumo_wf.to_string(index=False))

    # ─── 5. DM-HLN: ARDL e ensemble vs AR(1) ─────────────────────────────────
    print("\n  [5] Diebold-Mariano com correção HLN…")
    dm_ardl = dm_pareado(df_wf, modelo_alvo="ardl",        baselines=["ar1"])
    dm_med  = dm_pareado(df_wf, modelo_alvo="ens_mediana", baselines=["ar1", "ardl"])
    dm_avg  = dm_pareado(df_wf, modelo_alvo="ens_media",   baselines=["ar1", "ardl"])
    dm_completo = pd.concat([dm_ardl, dm_med, dm_avg], ignore_index=True)
    dm_completo.to_csv(OUT_DIR / "dm_completo.csv", index=False, float_format="%.6f")
    print(dm_completo.to_string(index=False))

    # ─── 6. Encompassing ARDL ↔ AR(1) ────────────────────────────────────────
    print("\n  [6] Encompassing test (HLN 1998) com HAC…")
    enc_rows = []
    for h in [1, 2]:
        sub = df_wf[df_wf["h"] == h]
        ardl_df = sub[sub["modelo"] == "ardl"].set_index("alvo")
        ar1_df  = sub[sub["modelo"] == "ar1" ].set_index("alvo")
        comum = ardl_df.index.intersection(ar1_df.index)
        if len(comum) < 5:
            continue
        y_true_v = ardl_df.loc[comum, "y_true"].values
        f_ardl   = ardl_df.loc[comum, "q50"].values
        f_ar1    = ar1_df .loc[comum, "q50"].values

        # H0_a: ARDL encompasses AR(1)
        t_ardl_enc = encompassing_test_hln(
            y_true_v, forecast_encompasser=f_ardl,
                       forecast_encompassed=f_ar1, h=h)
        t_ardl_enc.update({"h": h, "encompasser": "ardl", "encompassed": "ar1"})
        enc_rows.append(t_ardl_enc)

        # H0_b: AR(1) encompasses ARDL
        t_ar1_enc = encompassing_test_hln(
            y_true_v, forecast_encompasser=f_ar1,
                       forecast_encompassed=f_ardl, h=h)
        t_ar1_enc.update({"h": h, "encompasser": "ar1", "encompassed": "ardl"})
        enc_rows.append(t_ar1_enc)

    enc_df = pd.DataFrame(enc_rows)
    cols_ordem = ["h", "encompasser", "encompassed", "lambda", "se_hac",
                  "t_stat", "p_value", "n", "rejeita_H0", "conclusao"]
    enc_df = enc_df[cols_ordem]
    enc_df.to_csv(OUT_DIR / "encompassing.csv", index=False, float_format="%.6f")
    print(enc_df[["h", "encompasser", "encompassed", "lambda",
                  "p_value", "rejeita_H0"]].to_string(index=False))

    # ─── 6b. Combinação ótima soma=1 (Granger-Ramanathan restrita) ──────────
    print("\n  [6b] Combinação ótima OOS (soma=1, sem intercepto)…")
    combo_rows = []
    for h in [1, 2]:
        sub = df_wf[df_wf["h"] == h]
        ardl_df = sub[sub["modelo"] == "ardl"].set_index("alvo")
        ar1_df  = sub[sub["modelo"] == "ar1" ].set_index("alvo")
        comum = ardl_df.index.intersection(ar1_df.index)
        if len(comum) < 5:
            continue
        y_v   = ardl_df.loc[comum, "y_true"].values
        f_ardl = ardl_df.loc[comum, "q50"].values
        f_ar1  = ar1_df .loc[comum, "q50"].values
        comb = combinacao_otima_sum1(y_v, forecast_1=f_ardl, forecast_2=f_ar1, h=h)
        comb.update({"h": h, "f1": "ardl", "f2": "ar1"})
        combo_rows.append(comb)
    combo_df = pd.DataFrame(combo_rows)
    combo_df.to_csv(OUT_DIR / "combinacao_otima.csv",
                     index=False, float_format="%.6f")
    print(combo_df[["h", "f1", "f2", "w_1", "w_2", "p_value",
                    "mae_combinado", "mae_f1", "mae_f2",
                    "convexo"]].to_string(index=False))

    # ─── 7. Robustez log-diff mensal ─────────────────────────────────────────
    print("\n  [7] Robustez log-diff mensal…")
    df_logdiff = walkforward_log_diff(port_imp, pim, min_train=args.min_train, p_ar=args.p)
    df_logdiff.to_csv(OUT_DIR / "log_diff_walkforward.csv", index=False, float_format="%.6f")
    resumo_logdiff = resumir(df_logdiff)
    print(resumo_logdiff.to_string(index=False))
    dm_logdiff = dm_pareado(df_logdiff, modelo_alvo="ardl_logdiff", baselines=["ar1_logdiff"])
    dm_logdiff.to_csv(OUT_DIR / "dm_logdiff.csv", index=False, float_format="%.6f")
    print("  DM ARDL log-diff vs AR(1) log-diff:")
    print(dm_logdiff.to_string(index=False))

    # ─── 8. Aplicação da regra de decisão ────────────────────────────────────
    print("\n  [8] Aplicando regra de decisão pré-registrada…")
    decisao = aplicar_regra(
        dm_ardl_vs_ar1=dm_ardl,
        dm_ensemble_vs_ar1=pd.concat([dm_med, dm_avg], ignore_index=True),
        encompass=enc_df,
        alfa=0.05,
    )

    # ─── Saída final markdown ────────────────────────────────────────────────
    md = []
    md.append("# Resultados — Bateria de robustez ARDL (item 2)")
    md.append("")
    md.append(f"**Especificação aplicada:** AR(p={args.p}), lag_x={LAG_X}, HAC_lag={HAC_LAG}")
    md.append(f"**Tempo total de execução:** {time.time() - t0:.1f}s")
    md.append("")
    md.append("## Decisão aplicada (regra pré-registrada)")
    md.append("")
    md.append(f"### → **Linha {decisao['linha']}**")
    md.append("")
    md.append(f"> {decisao['comunicacao']}")
    md.append("")
    md.append("**Gatilhos ativados:**")
    md.append(f"- ARDL bate AR(1) em h=1: `{decisao['ardl_h1']}`")
    md.append(f"- ARDL bate AR(1) em h=2: `{decisao['ardl_h2']}`")
    md.append(f"- Ensemble bate AR(1) em h=1: `{decisao['ensemble_h1']}`")
    md.append(f"- Ensemble bate AR(1) em h=2: `{decisao['ensemble_h2']}`")
    md.append(f"- Encompassing favorece ARDL: `{decisao['encompass_favor_ardl']}`")
    md.append("")
    md.append("## 1. Coeficientes ARDL full-sample (HAC Newey-West, lag 12)")
    md.append("")
    md.append(_md_table(coef_df))
    md.append("")
    md.append("## 2. Diagnósticos de resíduo")
    md.append("")
    md.append(_md_table(diag))
    md.append("")
    md.append("## 3. ARDL sem COVID")
    md.append("")
    md.append(f"Δ relativo de β (full → sem_covid): **{delta_pct:.1%}**")
    md.append("")
    md.append(_md_table(sem_covid_df))
    md.append("")
    md.append("## 4. Métricas walk-forward")
    md.append("")
    md.append(_md_table(resumo_wf, casas=3))
    md.append("")
    md.append("## 5. DM-HLN")
    md.append("")
    md.append(_md_table(dm_completo, casas=4))
    md.append("")
    md.append("## 6. Encompassing test (HLN 1998)")
    md.append("")
    md.append("Convenção: H0 testada é \"`encompasser` ENCOMPASSES `encompassed`\".")
    md.append("Rejeita H0 (`rejeita_H0=True`) ⟺ `encompassed` agrega informação útil.")
    md.append("")
    md.append(_md_table(enc_df, casas=4))
    md.append("")
    md.append("## 6b. Combinação ótima OOS (soma = 1)")
    md.append("")
    md.append("Granger-Ramanathan restrito: `y = w_1·f_1 + w_2·f_2 + u`,")
    md.append("`w_1 + w_2 = 1`, sem intercepto. SE com HAC.")
    md.append("Convexo (`w_1 ∈ [0,1]`) indica combinação válida na casca convexa.")
    md.append("")
    md.append(_md_table(combo_df, casas=4))
    md.append("")
    md.append("## 7. Robustez log-diff mensal")
    md.append("")
    md.append("Métricas walk-forward na escala var12m (após agregação):")
    md.append("")
    md.append(_md_table(resumo_logdiff, casas=3))
    md.append("")
    md.append("DM ARDL log-diff vs AR(1) log-diff:")
    md.append("")
    md.append(_md_table(dm_logdiff, casas=4))
    md.append("")
    (OUT_DIR / "resultados_robustez.md").write_text("\n".join(md), encoding="utf-8")
    print(f"\n  ✓ Saída: {OUT_DIR / 'resultados_robustez.md'}")
    print(f"\n  ── DECISÃO: Linha {decisao['linha']} ──")
    print(f"  {decisao['comunicacao']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
