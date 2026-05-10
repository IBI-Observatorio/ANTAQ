"""
Dia 3 — Walk-forward DFM (PortGDP v2).

Para cada origem τ (jan/2018 → out/2025, ~95 pontos), com janela expansiva:

  1. Restringe painel ao treino: meses ≤ τ.
  2. Padroniza cada série (z-score) usando média e dp do treino — sem look-ahead.
  3. Ajusta DFM-1f e DFM-2f via Kalman MLE em statsmodels.
  4. Extrai fatores smoothed in-sample F_{t} para t ∈ [início, τ].
  5. Regressão de previsão (OLS HAC, lag=12):
        var12m(PIM)_{t+h} = α + γ' · F_{t+h-2} + ε
     onde h ∈ {1, 2}. Por construção F_{t+h-2} está dentro do treino
     quando h ≤ 2 (defasagem estrutural pré-registrada do v1).
  6. Previsão pontual + quantis empíricos dos resíduos in-sample.

Outputs:
    validacao/portgdp_v2/walkforward_dfm_previsoes.csv
    validacao/portgdp_v2/walkforward_dfm_log.csv  (convergência por origem)
"""
from __future__ import annotations

import argparse
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from analises.macro import pim_pf as carregar_pim_pf  # noqa: E402

OUT = ROOT / "validacao" / "portgdp_v2"
warnings.filterwarnings("ignore")

QUANTIS = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90]
LAG_F = 2     # defasagem estrutural pré-registrada
HAC_LAG = 12


# ─── Helpers ──────────────────────────────────────────────────────────────────
def _carregar_painel_var12m() -> pd.DataFrame:
    df = pd.read_parquet(OUT / "series_tratadas.parquet").set_index("mes")
    df.index = pd.to_datetime(df.index)
    cols = [c for c in df.columns if c.startswith("var12m__")]
    var = df[cols].dropna(how="all").copy()
    var.columns = [c.replace("var12m__", "") for c in var.columns]
    return var


def _carregar_pim_var12m() -> pd.Series:
    pim = carregar_pim_pf()
    return pim.pct_change(12).dropna().rename("pim_var12m")


def _zscore_treino(painel: pd.DataFrame, mes_corte: pd.Timestamp) -> pd.DataFrame:
    treino = painel.loc[:mes_corte]
    mu, sd = treino.mean(), treino.std(ddof=0).replace(0, np.nan)
    z = (painel - mu) / sd
    return z


def _ajustar_dfm(Y: np.ndarray, k_factors: int, factor_order: int,
                  start_params=None, maxiter: int = 500):
    """
    Cascata pragmática. Para k_factors=1: lbfgs converge bem.
    Para k_factors>1: lbfgs sistematicamente falha em painéis não-balanceados;
    pulamos direto para powell, que é robusto a má-condicionamento.

    Ordem:
      k=1 : [lbfgs (warm), powell, nm]
      k>1 : [powell (do zero), nm]
    """
    from statsmodels.tsa.statespace.dynamic_factor import DynamicFactor
    mod = DynamicFactor(Y, k_factors=k_factors, factor_order=factor_order,
                         error_order=0, error_var=False,
                         enforce_stationarity=True)

    if k_factors == 1:
        res = mod.fit(start_params=start_params, disp=False,
                       maxiter=maxiter, method="lbfgs")
        if res.mle_retvals.get("converged", False):
            return res
    res2 = mod.fit(disp=False, maxiter=maxiter, method="powell")
    if res2.mle_retvals.get("converged", False):
        return res2
    res3 = mod.fit(disp=False, maxiter=maxiter, method="nm")
    return res3 if res3.mle_retvals.get("converged", False) else res2


def _quantis_de_residuos(ponto: float, residuos: np.ndarray,
                          niveis=QUANTIS, escala=1.0) -> dict:
    if len(residuos) == 0 or not np.all(np.isfinite(residuos)):
        return {f"q{int(q*100):02d}": ponto for q in niveis} | {"media": ponto}
    q_resid = np.quantile(residuos, niveis) * escala
    return ({f"q{int(q*100):02d}": float(ponto + q_resid[i])
             for i, q in enumerate(niveis)}
            | {"media": float(ponto)})


# ─── Núcleo do walk-forward ───────────────────────────────────────────────────
def gerar_previsoes_origem(painel_var12m: pd.DataFrame,
                            pim_var12m: pd.Series,
                            origem: pd.Timestamp,
                            cache_params: dict,
                            horizontes=(1, 2)) -> tuple[list[dict], dict]:
    """
    Para uma origem τ: ajusta DFM-1f e DFM-2f, regressão de previsão para
    h ∈ horizontes. Retorna lista de registros (um por (h, modelo)).
    """
    z = _zscore_treino(painel_var12m, origem).loc[:origem]
    z = z.dropna(how="any")          # só meses com TODAS as séries observadas
    if len(z) < 30:
        return [], {"origem": origem, "n_obs": len(z), "status": "treino_insuficiente"}

    Y = z.values
    registros = []
    log_origem = {"origem": origem, "n_obs": len(z)}

    for nome, k, ordem in [("dfm_1f", 1, 2), ("dfm_2f", 2, 1)]:
        try:
            sp = cache_params.get(nome)
            res = _ajustar_dfm(Y, k_factors=k, factor_order=ordem, start_params=sp)
            if not res.mle_retvals.get("converged", True):
                log_origem[f"{nome}_status"] = "nao_convergiu"
                continue
            cache_params[nome] = res.params
            log_origem[f"{nome}_status"] = "ok"
            log_origem[f"{nome}_iter"] = int(res.mle_retvals.get("iterations", -1))
        except Exception as e:
            log_origem[f"{nome}_status"] = f"erro:{type(e).__name__}"
            continue

        # Fatores smoothed in-sample (k × T)
        F = res.smoothed_state[:k]
        F = pd.DataFrame(F.T, index=z.index,
                          columns=[f"f{i+1}" for i in range(k)])

        for h in horizontes:
            # Construir regressão: pim_{t+h} ~ α + γ·F_{t+h-LAG_F}
            # Equivale a alinhar F.shift(LAG_F - h) com pim
            F_lagged = F.shift(LAG_F - h)
            df_reg = pd.concat([pim_var12m.rename("y"), F_lagged], axis=1).dropna()
            df_reg = df_reg.loc[df_reg.index <= origem]
            if len(df_reg) < 20:
                continue

            import statsmodels.api as sm
            X = sm.add_constant(df_reg[F.columns].values)
            y_train = df_reg["y"].values
            try:
                ols = sm.OLS(y_train, X).fit(cov_type="HAC",
                                              cov_kwds={"maxlags": HAC_LAG})
            except Exception as e:
                log_origem[f"{nome}_h{h}_status"] = f"ols_falhou:{type(e).__name__}"
                continue

            # Previsão pontual: usa F na linha de origem para prever PIM em τ+h.
            # F_lagged.loc[τ+h] é o que precisamos, mas τ+h não está no índice.
            # Equivalente: F.loc[τ+h-LAG_F]. Para h=1: F.loc[τ-1]. Para h=2: F.loc[τ].
            pos_factor = origem - pd.DateOffset(months=LAG_F - h)
            if pos_factor not in F.index:
                continue
            x_alvo = np.concatenate([[1.0], F.loc[pos_factor].values])
            pred = float(x_alvo @ ols.params)
            resid = y_train - X @ ols.params
            quantis = _quantis_de_residuos(pred, resid, niveis=QUANTIS,
                                            escala=np.sqrt(h))

            registros.append({
                "origem": origem,
                "alvo":   origem + pd.DateOffset(months=h),
                "h":      h,
                "modelo": nome,
                "y_true": float(pim_var12m.get(origem + pd.DateOffset(months=h),
                                                np.nan)),
                **quantis,
                "q50":    quantis.get("q50", quantis["media"]),
            })

    return registros, log_origem


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-train", type=int, default=36,
                        help="meses mínimos no treino (default 36, mesmo do v1)")
    parser.add_argument("--max-origens", type=int, default=None,
                        help="limita número de origens (debug)")
    args = parser.parse_args()

    print("\n  ── Dia 3 — Walk-forward DFM ──")
    t0 = time.time()
    painel = _carregar_painel_var12m()
    pim = _carregar_pim_var12m()

    inicio_pim = pim.index.min()
    inicio_painel = painel.index.min()
    inicio_comum = max(inicio_pim, inicio_painel)
    fim_comum = min(pim.index.max(), painel.index.max())
    print(f"    Janela comum: {inicio_comum.date()} → {fim_comum.date()}")

    # Origens válidas: depois de min_train meses, pelo menos 2 meses para frente
    origens_todas = pim.index[(pim.index >= inicio_comum) & (pim.index <= fim_comum)]
    primeira_origem = origens_todas[args.min_train]
    ultima_origem = origens_todas[-3]
    origens = origens_todas[(origens_todas >= primeira_origem) &
                              (origens_todas <= ultima_origem)]
    if args.max_origens:
        origens = origens[: args.max_origens]
    print(f"    Origens: {len(origens)} ({origens[0].date()} → {origens[-1].date()})")

    todos_registros = []
    log_completo = []
    cache_params = {}    # warm-start: parâmetros da origem anterior

    for i, origem in enumerate(origens):
        regs, log = gerar_previsoes_origem(painel, pim, origem, cache_params)
        todos_registros.extend(regs)
        log_completo.append(log)
        if (i + 1) % 10 == 0 or i == len(origens) - 1:
            elapsed = time.time() - t0
            taxa = (i + 1) / elapsed
            eta = (len(origens) - i - 1) / taxa
            print(f"    [{i+1:>3}/{len(origens)}] {origem.date()}  "
                  f"({elapsed:.0f}s · ETA {eta:.0f}s)")

    print(f"\n  Walk-forward concluído em {time.time()-t0:.0f}s.")
    print(f"  {len(todos_registros)} previsões geradas.")

    df_pred = pd.DataFrame(todos_registros)
    df_pred.to_csv(OUT / "walkforward_dfm_previsoes.csv",
                    index=False, float_format="%.6f")
    df_log = pd.DataFrame(log_completo)
    df_log.to_csv(OUT / "walkforward_dfm_log.csv", index=False)
    print(f"  ✓ {(OUT / 'walkforward_dfm_previsoes.csv').relative_to(ROOT)}")
    print(f"  ✓ {(OUT / 'walkforward_dfm_log.csv').relative_to(ROOT)}")

    # Sanity log de convergência
    n_total = len(df_log)
    for nome in ["dfm_1f", "dfm_2f"]:
        col = f"{nome}_status"
        if col in df_log.columns:
            n_ok = int((df_log[col] == "ok").sum())
            print(f"    {nome}: {n_ok}/{n_total} origens convergiram ({n_ok/n_total:.0%})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
