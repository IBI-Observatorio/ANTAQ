"""
Gera a previsão mensal do PIM-PF Combinado IBI.

Pipeline:
  1. Carrega painel ANTAQ tratado mais recente (snapshot do dia ou
     series_tratadas.parquet).
  2. Carrega modelo DFM treinado mais recente em models/dfm_atual.pkl
     (refit anual — ver pipelines/pimpf_combinado/refit_anual.py).
  3. Aplica o DFM via Kalman smoother — extrai fator F_t na origem.
  4. Estima previsão pontual t+2 e t+1 via regressão γ·F_{τ+h-2} sobre
     a janela expansiva, com HAC Newey-West (lag 12).
  5. Estima/atualiza pesos GR rolling (expanding window) e gera
     combinação t+2 (publicada) e t+1 (interna).
  6. Calibra intervalo conformal split padrão sobre erros históricos
     da combinação.
  7. Append em data/previsoes/historico.csv com tipo=producao,
     idempotente (não duplica linha do mesmo dia).

Uso:
    python -m pipelines.pimpf_combinado.gera_previsao
    python -m pipelines.pimpf_combinado.gera_previsao --data 2026-05-05
"""
from __future__ import annotations

import argparse
import csv
import pickle
import sys
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from analises.macro import sgs                       # noqa: E402

OUT     = ROOT / "data" / "previsoes" / "historico.csv"
MODELS  = ROOT / "models"
SERIES  = ROOT / "validacao" / "portgdp_v2" / "series_tratadas.parquet"
SNAP_PIMPF = ROOT / "data" / "snapshots" / "pimpf"

QUANTIS_NIV = (0.10, 0.90)
LAG_F = 2
ALPHA_CONF = 0.20
HAC_LAG = 12

warnings.filterwarnings("ignore")


COLUNAS_HIST = [
    "data_emissao", "mes_alvo", "horizonte", "previsao_pontual",
    "intervalo_inferior_80", "intervalo_superior_80",
    "peso_dfm", "tipo", "realizado", "erro", "dentro_intervalo",
    "modelo_dfm", "ultima_obs_pim_pf",
]


def _carregar_modelo() -> dict:
    arq = MODELS / "dfm_atual.pkl"
    if not arq.exists():
        raise FileNotFoundError(
            f"falta {arq} — rode refit_anual.py antes")
    with open(arq, "rb") as f:
        return pickle.load(f)


def _carregar_painel_var12m() -> pd.DataFrame:
    df = pd.read_parquet(SERIES).set_index("mes")
    df.index = pd.to_datetime(df.index)
    cols = [c for c in df.columns if c.startswith("var12m__")]
    var = df[cols].dropna(how="all").copy()
    var.columns = [c.replace("var12m__", "") for c in var.columns]
    return var


def _carregar_pim_var12m_e_idx() -> tuple[pd.Series, pd.Series]:
    pim = sgs(28503)
    pim_idx = pim / pim.loc["2014-01":"2014-12"].mean() * 100
    return pim_idx.pct_change(12).dropna().rename("pim_var12m"), pim_idx


def _zscore_treino(painel: pd.DataFrame, mes_corte: pd.Timestamp) -> pd.DataFrame:
    """Padroniza com média e dp do treino (≤ mes_corte) — sem look-ahead."""
    treino = painel.loc[:mes_corte]
    mu, sd = treino.mean(), treino.std(ddof=0).replace(0, np.nan)
    return (painel - mu) / sd


def _aplicar_kalman_smoother(modelo, Y_padronizado: np.ndarray) -> np.ndarray:
    """Aplica o DFM já estimado a um painel novo via Kalman smoother.
    Retorna fator smoothed (T,) — k_factors=1 implícito.
    """
    from statsmodels.tsa.statespace.dynamic_factor import DynamicFactor
    novo = DynamicFactor(Y_padronizado, k_factors=1, factor_order=2,
                          error_order=0, error_var=False,
                          enforce_stationarity=True)
    novo_smoothed = novo.smooth(modelo.params)
    return novo_smoothed.smoothed_state[0]


def _previsao_dfm(F: np.ndarray, fechas: pd.DatetimeIndex,
                   pim_var: pd.Series, h: int) -> tuple[float, np.ndarray]:
    """Regressão expanding `pim_var ~ const + γ·F_{t-LAG_F+h}` com HAC.
    Retorna (previsão_pontual, residuos_in_sample)."""
    import statsmodels.api as sm
    pos_origem = len(F) - 1
    pos_feature = pos_origem + h - LAG_F
    if pos_feature < 0 or pos_feature >= len(F):
        return float("nan"), np.array([])

    F_lagged = pd.Series(F, index=fechas).shift(LAG_F - h)
    df_reg = pd.concat([pim_var.rename("y"),
                         F_lagged.rename("f")], axis=1).dropna()
    df_reg = df_reg.loc[df_reg.index <= fechas[-1]]
    if len(df_reg) < 12:
        return float("nan"), np.array([])

    X = sm.add_constant(df_reg["f"].values)
    y_train = df_reg["y"].values
    res = sm.OLS(y_train, X).fit(cov_type="HAC",
                                    cov_kwds={"maxlags": HAC_LAG})
    x_alvo = np.array([1.0, float(F[pos_feature])])
    pred = float(x_alvo @ res.params)
    residuos = y_train - X @ res.params
    return pred, residuos


def _previsao_ar1(pim_var: pd.Series, h: int) -> tuple[float, np.ndarray]:
    """AR(1) iterativo até h passos. Retorna (ponto, residuos_1passo)."""
    y = pim_var.dropna().values
    if len(y) < 5:
        return float("nan"), np.array([])
    Y, X = y[1:], y[:-1]
    phi, alpha = np.polyfit(X, Y, 1)
    y_hat = float(y[-1])
    for _ in range(h):
        y_hat = alpha + phi * y_hat
    res = Y - (alpha + phi * X)
    return y_hat, res


def _peso_gr_rolling(pim_var: pd.Series, F: np.ndarray,
                       fechas: pd.DatetimeIndex, h: int = 2,
                       min_treino: int = 36) -> tuple[float, int]:
    """
    Reestima peso ótimo GR (soma=1, sem intercepto) com expanding window
    sobre os pares (y_t, f_dfm_t, f_ar1_t) que poderíamos ter gerado em
    cada origem ≤ T-1. Retorna (peso_dfm_atual, n_origens_usadas).
    """
    n = len(fechas)
    pares_dfm, pares_ar1, alvos = [], [], []
    for i in range(min_treino, n - h):
        origem_idx = i
        feature_idx = origem_idx + h - LAG_F
        target_idx  = origem_idx + h
        if feature_idx < 0 or target_idx >= n:
            continue
        if target_idx not in range(len(pim_var)):
            continue
        try:
            y_true = pim_var.iloc[target_idx]
        except IndexError:
            continue
        # DFM: regressão expanding até origem
        pred_dfm, _ = _previsao_dfm(F[: origem_idx + 1],
                                       fechas[: origem_idx + 1],
                                       pim_var.iloc[: origem_idx + 1], h)
        # AR(1) expanding até origem
        pred_ar1, _ = _previsao_ar1(pim_var.iloc[: origem_idx + 1], h)
        if not (np.isfinite(pred_dfm) and np.isfinite(pred_ar1)
                 and np.isfinite(y_true)):
            continue
        pares_dfm.append(pred_dfm)
        pares_ar1.append(pred_ar1)
        alvos.append(float(y_true))
    if len(alvos) < 5:
        return 0.5, len(alvos)
    arr_dfm = np.asarray(pares_dfm)
    arr_ar1 = np.asarray(pares_ar1)
    arr_y   = np.asarray(alvos)
    # OLS sem intercepto: w = sum(X*Y)/sum(X*X), restringe [0,1]
    X = arr_dfm - arr_ar1
    Y = arr_y - arr_ar1
    denom = float(np.sum(X * X))
    w = (float(np.sum(X * Y)) / denom) if denom > 0 else 0.5
    return float(np.clip(w, 0.0, 1.0)), len(alvos)


def _quantil_conformal(erros_abs_calib: np.ndarray, alfa: float) -> float:
    n = len(erros_abs_calib)
    if n == 0:
        return float("nan")
    k = min(int(np.ceil((n + 1) * (1 - alfa))), n)
    return float(np.sort(erros_abs_calib)[k - 1])


def _registrar(linha: dict) -> bool:
    """Append idempotente — não duplica registro com mesma chave
    (data_emissao, mes_alvo, horizonte, tipo)."""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    novo = not OUT.exists()
    if not novo:
        df = pd.read_csv(OUT)
        chave = ((df["data_emissao"] == linha["data_emissao"]) &
                  (df["mes_alvo"]     == linha["mes_alvo"]) &
                  (df["horizonte"]    == linha["horizonte"]) &
                  (df["tipo"]         == linha["tipo"]))
        if chave.any():
            print(f"    [{linha['horizonte']}] já registrado: "
                  f"{linha['data_emissao']} → {linha['mes_alvo']}")
            return False
    with open(OUT, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS_HIST)
        if novo:
            w.writeheader()
        # garante todas as colunas
        for c in COLUNAS_HIST:
            linha.setdefault(c, "")
        w.writerow(linha)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=None,
                        help="Data de emissão (AAAA-MM-DD). Default: hoje UTC.")
    args = parser.parse_args()

    data_emissao = args.data or datetime.utcnow().strftime("%Y-%m-%d")
    print(f"\n  ── gera_previsao — emissão {data_emissao} ──")

    print("  [1] Carregando modelo DFM atual…")
    modelo_payload = _carregar_modelo()
    modelo = modelo_payload["modelo_serializado"]
    ano_modelo = modelo_payload["ano_refit"]
    print(f"      DFM treinado em {ano_modelo} "
          f"(corte {modelo_payload['data_corte'][:10]})")

    print("  [2] Carregando painel var12m…")
    painel = _carregar_painel_var12m()
    print(f"      {painel.shape[0]} meses × {painel.shape[1]} séries")

    print("  [3] Carregando PIM-PF (var12m e índice)…")
    pim_var, pim_idx = _carregar_pim_var12m_e_idx()
    print(f"      Última obs PIM-PF: {pim_var.index[-1].date()}")

    # Alinhamento
    idx_comum = painel.dropna(how="any").index.intersection(pim_var.index)
    if len(idx_comum) < 36:
        raise RuntimeError("janela insuficiente para previsão.")
    origem = idx_comum.max()
    print(f"      Origem da previsão: {origem.date()}")

    # Padronização sem look-ahead
    z = _zscore_treino(painel, origem).loc[:origem].dropna(how="any")

    print("  [4] Aplicando Kalman smoother…")
    F = _aplicar_kalman_smoother(modelo, z.values)

    print("  [5] Previsões h=1 e h=2…")
    pim_var_ate = pim_var.loc[:origem]
    pred_dfm_h2, resid_dfm_h2 = _previsao_dfm(F, z.index, pim_var_ate, h=2)
    pred_dfm_h1, _            = _previsao_dfm(F, z.index, pim_var_ate, h=1)
    pred_ar1_h2, resid_ar1_h2 = _previsao_ar1(pim_var_ate, h=2)
    pred_ar1_h1, _            = _previsao_ar1(pim_var_ate, h=1)

    print("  [6] Pesos GR rolling…")
    w_h2, n_h2 = _peso_gr_rolling(pim_var_ate, F, z.index, h=2)
    w_h1, n_h1 = _peso_gr_rolling(pim_var_ate, F, z.index, h=1)
    print(f"      h=1: w_DFM = {w_h1:.3f}  ({n_h1} origens)")
    print(f"      h=2: w_DFM = {w_h2:.3f}  ({n_h2} origens)")

    pred_comb_h2 = w_h2 * pred_dfm_h2 + (1 - w_h2) * pred_ar1_h2
    pred_comb_h1 = w_h1 * pred_dfm_h1 + (1 - w_h1) * pred_ar1_h1

    print("  [7] Intervalo conformal 80% (split padrão)…")
    # Resíduos da combinação como aproximação de erros históricos
    n_erros = min(len(resid_dfm_h2), len(resid_ar1_h2))
    err_comb = (w_h2 * resid_dfm_h2[-n_erros:]
                 + (1 - w_h2) * resid_ar1_h2[-n_erros:])
    metade = max(len(err_comb) // 2, 12)
    erros_calib = np.abs(err_comb[:metade])
    q_h2 = _quantil_conformal(erros_calib, ALPHA_CONF)

    n_erros1 = min(len(resid_dfm_h2), len(resid_ar1_h2))      # h=1 reusa
    err_comb1 = (w_h1 * resid_dfm_h2[-n_erros1:]
                  + (1 - w_h1) * resid_ar1_h2[-n_erros1:])
    erros_calib1 = np.abs(err_comb1[:max(len(err_comb1)//2, 12)])
    q_h1 = _quantil_conformal(erros_calib1, ALPHA_CONF)

    # Conversão da var12m de volta para nível do índice
    def _para_nivel(t_alvo, var_pred, var_low, var_high):
        t_base = t_alvo - pd.DateOffset(months=12)
        if t_base not in pim_idx.index or pd.isna(pim_idx.loc[t_base]):
            return None
        base = float(pim_idx.loc[t_base])
        return {
            "ponto": base * (1 + var_pred),
            "low":   base * (1 + var_pred - q_h2),
            "high":  base * (1 + var_pred + q_h2),
        }

    print("  [8] Registrando previsões em historico.csv…")
    mes_h2 = origem + pd.DateOffset(months=2)
    mes_h1 = origem + pd.DateOffset(months=1)

    # h=2 (PUBLICADO)
    _registrar({
        "data_emissao":           data_emissao,
        "mes_alvo":               mes_h2.strftime("%Y-%m-%d"),
        "horizonte":              2,
        "previsao_pontual":       round(pred_comb_h2, 6),
        "intervalo_inferior_80":  round(pred_comb_h2 - q_h2, 6),
        "intervalo_superior_80":  round(pred_comb_h2 + q_h2, 6),
        "peso_dfm":               round(w_h2, 4),
        "tipo":                   "producao",
        "realizado":              "",
        "erro":                   "",
        "dentro_intervalo":       "",
        "modelo_dfm":             f"dfm_{ano_modelo}",
        "ultima_obs_pim_pf":      origem.strftime("%Y-%m-%d"),
    })

    # h=1 (INTERNO — não publicado no card, mas disponível)
    _registrar({
        "data_emissao":           data_emissao,
        "mes_alvo":               mes_h1.strftime("%Y-%m-%d"),
        "horizonte":              1,
        "previsao_pontual":       round(pred_comb_h1, 6),
        "intervalo_inferior_80":  round(pred_comb_h1 - q_h1, 6),
        "intervalo_superior_80":  round(pred_comb_h1 + q_h1, 6),
        "peso_dfm":               round(w_h1, 4),
        "tipo":                   "producao",
        "realizado":              "",
        "erro":                   "",
        "dentro_intervalo":       "",
        "modelo_dfm":             f"dfm_{ano_modelo}",
        "ultima_obs_pim_pf":      origem.strftime("%Y-%m-%d"),
    })

    print(f"\n  ✓ Previsões emitidas:")
    print(f"      h=2 → {mes_h2.date()}: var12m = {pred_comb_h2*100:+.2f} pp "
          f"(IC 80% [{(pred_comb_h2-q_h2)*100:+.2f}, {(pred_comb_h2+q_h2)*100:+.2f}])")
    print(f"      h=1 → {mes_h1.date()}: var12m = {pred_comb_h1*100:+.2f} pp "
          f"(IC 80% [{(pred_comb_h1-q_h1)*100:+.2f}, {(pred_comb_h1+q_h1)*100:+.2f}])")
    print(f"  ✓ {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
