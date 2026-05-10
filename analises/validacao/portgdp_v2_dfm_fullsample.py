"""
Dia 2 — DFM full-sample para sanity check.

Estima DFM-1f (1 fator, AR(2)) e DFM-2f (2 fatores, VAR(1)) sobre as 35
séries var12m padronizadas. Reporta loadings e fatores estimados.

⚠ Pré-registro: este passo é PARA INSPEÇÃO de loadings e interpretação
econômica (sanity), NÃO para decisão de qual variante usar. As duas
variantes prosseguem para o walk-forward independente do que se vê aqui.

Outputs:
    validacao/portgdp_v2/loadings_fatores.csv
    validacao/portgdp_v2/fatores_estimados.csv
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "validacao" / "portgdp_v2"

warnings.filterwarnings("ignore")


def _carregar_var12m_padronizado() -> pd.DataFrame:
    df = pd.read_parquet(OUT / "series_tratadas.parquet").set_index("mes")
    df.index = pd.to_datetime(df.index)
    cols_v = [c for c in df.columns if c.startswith("var12m__")]
    var12m = df[cols_v].dropna(how="all")
    var12m.columns = [c.replace("var12m__", "") for c in var12m.columns]
    # Padronização full-sample (apenas para sanity full-sample!)
    z = (var12m - var12m.mean()) / var12m.std(ddof=0)
    return z.dropna()  # remove leading NaNs do var12m


def estimar_dfm(Y: pd.DataFrame, k_factors: int, factor_order: int,
                 maxiter: int = 500):
    """Ajusta DynamicFactor com Kalman MLE."""
    from statsmodels.tsa.statespace.dynamic_factor import DynamicFactor
    mod = DynamicFactor(Y.values,
                         k_factors=k_factors,
                         factor_order=factor_order,
                         error_order=0,
                         error_var=False,
                         enforce_stationarity=True)
    res = mod.fit(disp=False, maxiter=maxiter)
    return res


def main() -> int:
    print("\n  ── Dia 2 — DFM full-sample (sanity) ──")
    Y = _carregar_var12m_padronizado()
    print(f"    Painel padronizado: {Y.shape[0]} meses × {Y.shape[1]} séries")
    print(f"    Janela: {Y.index[0].date()} → {Y.index[-1].date()}")

    loadings_all = []
    fatores_all = pd.DataFrame(index=Y.index)

    for nome, k, ordem in [("dfm_1f", 1, 2), ("dfm_2f", 2, 1)]:
        print(f"\n  Ajustando {nome} (k_factors={k}, factor_order={ordem})…")
        try:
            res = estimar_dfm(Y, k_factors=k, factor_order=ordem)
        except Exception as e:
            print(f"    ✗ Falhou: {e}")
            continue
        print(f"    LL = {res.llf:.2f}, AIC = {res.aic:.1f}, "
              f"BIC = {res.bic:.1f}, iterações = {res.mle_retvals.get('iterations', '?')}")
        if not res.mle_retvals.get("converged", True):
            print("    ⚠ NÃO CONVERGIU.")

        # Loadings: matriz Z de design tem shape (n_obs_eq, k_states), onde
        # k_states = k_factors × factor_order (estado inclui lags). Apenas as
        # primeiras k_factors colunas têm loadings observacionais.
        Z = res.filter_results.design[..., 0]
        Z_obs = Z[:, :k]
        df_load = pd.DataFrame(Z_obs, index=Y.columns,
                                columns=[f"f{i+1}" for i in range(k)])
        df_load["modelo"] = nome
        df_load["chave"] = df_load.index
        loadings_all.append(df_load.reset_index(drop=True))

        # Fatores estimados (smoothed)
        fac_smoothed = res.smoothed_state[:k]   # k × T
        for i in range(k):
            col = f"{nome}_f{i+1}"
            fatores_all[col] = pd.Series(fac_smoothed[i], index=Y.index)

        # Sanity: variância explicada média
        # (não usar para selecionar — só log)
        Yhat = res.fittedvalues
        ss_res = float(np.nansum((Y.values - Yhat) ** 2))
        ss_tot = float(np.nansum(Y.values ** 2))
        r2_painel = 1 - ss_res / ss_tot
        print(f"    R² agregado (in-sample): {r2_painel:.3f}")

        # Top loadings absolutos por fator (sanity econômica)
        for i in range(k):
            top = df_load.set_index("chave")[f"f{i+1}"].abs().nlargest(5)
            print(f"    Top 5 loadings |f{i+1}|:")
            for chave, v in top.items():
                sinal = "+" if df_load.set_index("chave").loc[chave, f"f{i+1}"] > 0 else "−"
                print(f"      {sinal}{abs(df_load.set_index('chave').loc[chave, f'f{i+1}']):.3f}  {chave}")

    # Salva
    if loadings_all:
        pd.concat(loadings_all, ignore_index=True).to_csv(
            OUT / "loadings_fatores.csv", index=False, float_format="%.6f")
        print(f"\n  ✓ {(OUT / 'loadings_fatores.csv').relative_to(ROOT)}")
    fatores_all.reset_index().to_csv(
        OUT / "fatores_estimados.csv", index=False, float_format="%.6f")
    print(f"  ✓ {(OUT / 'fatores_estimados.csv').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
