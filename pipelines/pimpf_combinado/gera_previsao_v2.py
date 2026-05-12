"""
Pipeline v2 — variante experimental do PIM-PF Combinado IBI.

Mudanças vs v1 (pré-registrado):
  1. Painel ampliado: ANTAQ (35 séries) + IBC-Br + IPCA + Selic (3 séries macro).
  2. DFM com k_factors=2 (captura componentes cíclicos distintos).
  3. AR(1) robusto:
       - âncora = mediana das últimas 3 observações (em vez da última).
       - shrinkage: se última obs |z-score| > 2.0 sobre 24m, puxa
         a previsão para a média móvel 24m com peso ~0.3.
  4. Combinação GR rolling igual ao v1.

Saída paralela (não substitui v1):
  - models/dfm_v2_atual.pkl
  - data/previsoes/historico_v2.csv

Uso:
    python -m pipelines.pimpf_combinado.gera_previsao_v2
    python -m pipelines.pimpf_combinado.gera_previsao_v2 --data 2026-05-12
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

from analises.macro import pim_pf as _pim_pf, ibc_br, ipca_mensal  # noqa: E402

OUT     = ROOT / "data" / "previsoes" / "historico_v2.csv"
MODELS  = ROOT / "models"
SERIES  = ROOT / "validacao" / "portgdp_v2" / "series_tratadas.parquet"

LAG_F = 2
ALPHA_CONF = 0.20
HAC_LAG = 12
K_FACTORS = 2          # v2: 2 fatores em vez de 1
JANELA_ROBUSTA = 3     # mediana das últimas 3 obs como âncora do AR(1)
JANELA_SHRINK  = 24    # janela para z-score e média de shrinkage
THR_OUTLIER    = 2.0   # |z-score| > 2 → outlier
ALPHA_SHRINK   = 0.30  # peso na média móvel quando última obs é outlier

warnings.filterwarnings("ignore")


COLUNAS_HIST = [
    "data_emissao", "mes_alvo", "horizonte", "previsao_pontual",
    "intervalo_inferior_80", "intervalo_superior_80",
    "peso_dfm", "tipo", "realizado", "erro", "dentro_intervalo",
    "modelo_dfm", "ultima_obs_pim_pf",
]


# ─── Painel ampliado: ANTAQ + macro ───────────────────────────────────────
def _carregar_painel_var12m_ampliado() -> pd.DataFrame:
    """Painel ANTAQ (var12m das 35 séries) + 3 séries macro em var12m."""
    df = pd.read_parquet(SERIES).set_index("mes")
    df.index = pd.to_datetime(df.index)
    cols = [c for c in df.columns if c.startswith("var12m__")]
    var = df[cols].copy()
    var.columns = [c.replace("var12m__", "") for c in var.columns]

    # Séries macro: var12m do nível mensal
    ibc = ibc_br().resample("MS").last()
    ipc = ipca_mensal().resample("MS").last()

    macro = pd.DataFrame({
        "macro_ibc_br":   ibc.pct_change(12),
        "macro_ipca":     ipc.pct_change(12),
    })
    macro.index = pd.to_datetime(macro.index)

    # Junta no índice do painel ANTAQ; macro fica como colunas extras
    painel = var.join(macro, how="left")
    return painel


def _zscore_treino(painel: pd.DataFrame, mes_corte: pd.Timestamp) -> pd.DataFrame:
    treino = painel.loc[:mes_corte]
    mu, sd = treino.mean(), treino.std(ddof=0).replace(0, np.nan)
    return (painel - mu) / sd


# ─── DFM com k_factors=2 ──────────────────────────────────────────────────
def _ajustar_dfm_v2(Y: np.ndarray, k_factors: int = K_FACTORS):
    """Tenta convergência em duas etapas: EM (warm-start) → BFGS."""
    from statsmodels.tsa.statespace.dynamic_factor import DynamicFactor
    mod = DynamicFactor(Y, k_factors=k_factors, factor_order=2,
                         error_order=0, error_var=False,
                         enforce_stationarity=True)
    try:
        warm = mod.fit_em(disp=False, maxiter=50)
        res = mod.fit(start_params=warm.params,
                       disp=False, maxiter=500, method="lbfgs")
        if not res.mle_retvals.get("converged", False):
            res = mod.fit(start_params=warm.params,
                           disp=False, maxiter=500, method="powell")
        return res
    except Exception:
        # fallback puro BFGS com mais iterações
        return mod.fit(disp=False, maxiter=1000, method="lbfgs")


def _treinar_ou_carregar_dfm_v2(Y: np.ndarray, ano_alvo: int):
    arq = MODELS / f"dfm_v2_{ano_alvo}.pkl"
    atual = MODELS / "dfm_v2_atual.pkl"
    if arq.exists():
        print(f"      Usando DFM v2 existente: {arq.relative_to(ROOT)}")
        with open(arq, "rb") as f:
            return pickle.load(f), arq
    print(f"      Treinando DFM v2 (k_factors={K_FACTORS})…")
    k_usado = K_FACTORS
    res = _ajustar_dfm_v2(Y, k_factors=K_FACTORS)
    if not res.mle_retvals.get("converged", False):
        print(f"      ⚠ k_factors={K_FACTORS} não convergiu — fallback k=1")
        from statsmodels.tsa.statespace.dynamic_factor import DynamicFactor
        m1 = DynamicFactor(Y, k_factors=1, factor_order=2,
                            error_order=0, error_var=False,
                            enforce_stationarity=True)
        res = m1.fit(disp=False, maxiter=500)
        k_usado = 1
        if not res.mle_retvals.get("converged", False):
            raise RuntimeError(f"DFM v2 não convergiu (ano {ano_alvo})")
    arq.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "modelo_serializado": res,
        "k_factors":          k_usado,
        "ano_refit":          ano_alvo,
        "n_meses":            int(Y.shape[0]),
        "n_series":           int(Y.shape[1]),
        "data_refit_utc":     datetime.utcnow().isoformat(),
    }
    with open(arq, "wb") as f:
        pickle.dump(payload, f)
    import shutil
    shutil.copyfile(arq, atual)
    print(f"      ✓ {arq.relative_to(ROOT)}")
    return payload, arq


def _kalman_smoother_factor(modelo, Y_padronizado: np.ndarray,
                              k_factors: int) -> np.ndarray:
    """Retorna fator(es) smoothed shape (k_factors, T)."""
    from statsmodels.tsa.statespace.dynamic_factor import DynamicFactor
    novo = DynamicFactor(Y_padronizado, k_factors=k_factors, factor_order=2,
                          error_order=0, error_var=False,
                          enforce_stationarity=True)
    sm = novo.smooth(modelo.params)
    return sm.smoothed_state[:k_factors]


# ─── PIM-PF e regressão DFM → var12m ──────────────────────────────────────
def _carregar_pim_var12m_e_idx() -> tuple[pd.Series, pd.Series]:
    pim = _pim_pf()
    pim_idx = pim / pim.loc["2014-01":"2014-12"].mean() * 100
    return pim_idx.pct_change(12).dropna().rename("pim_var12m"), pim_idx


def _previsao_dfm(F: np.ndarray, fechas: pd.DatetimeIndex,
                    pim_var: pd.Series, h: int) -> tuple[float, np.ndarray]:
    """Regressão pim_var ~ const + γ·F_{t-LAG_F+h} expanding, com HAC.
    F tem shape (k_factors, T)."""
    import statsmodels.api as sm
    if F.ndim == 1:
        F = F.reshape(1, -1)
    n = F.shape[1]
    pos_origem = n - 1
    pos_feature = pos_origem + h - LAG_F
    if pos_feature < 0 or pos_feature >= n:
        return float("nan"), np.array([])

    df_f = pd.DataFrame(F.T, index=fechas,
                          columns=[f"f{i}" for i in range(F.shape[0])])
    df_f_lagged = df_f.shift(LAG_F - h)
    df_reg = pd.concat([pim_var.rename("y"), df_f_lagged], axis=1).dropna()
    df_reg = df_reg.loc[df_reg.index <= fechas[-1]]
    if len(df_reg) < 12:
        return float("nan"), np.array([])

    X = sm.add_constant(df_reg[df_f.columns].values)
    y_train = df_reg["y"].values
    res = sm.OLS(y_train, X).fit(cov_type="HAC",
                                    cov_kwds={"maxlags": HAC_LAG})
    x_alvo = np.array([1.0] + [float(F[i, pos_feature])
                                  for i in range(F.shape[0])])
    pred = float(x_alvo @ res.params)
    residuos = y_train - X @ res.params
    return pred, residuos


# ─── AR(1) ROBUSTO (mudança chave do v2) ──────────────────────────────────
def _previsao_ar1_robusto(pim_var: pd.Series, h: int) -> tuple[float, np.ndarray]:
    """
    AR(1) com:
      - âncora = mediana das últimas JANELA_ROBUSTA observações (vs. apenas y_T).
      - shrinkage: se |z-score(y_T)| sobre últimas JANELA_SHRINK > THR_OUTLIER,
        puxa previsão para a média de JANELA_SHRINK com peso ALPHA_SHRINK.
    """
    y = pim_var.dropna().values
    if len(y) < max(JANELA_ROBUSTA, JANELA_SHRINK) + 1:
        # fallback ao AR(1) clássico
        if len(y) < 5:
            return float("nan"), np.array([])
        Y, X = y[1:], y[:-1]
        phi, alpha = np.polyfit(X, Y, 1)
        y_hat = float(y[-1])
        for _ in range(h):
            y_hat = alpha + phi * y_hat
        res = Y - (alpha + phi * X)
        return y_hat, res

    # Estima AR(1) clássico (coeficientes)
    Y, X = y[1:], y[:-1]
    phi, alpha = np.polyfit(X, Y, 1)
    res = Y - (alpha + phi * X)

    # Âncora robusta: mediana das últimas JANELA_ROBUSTA obs
    ancora = float(np.median(y[-JANELA_ROBUSTA:]))

    # Detecção de outlier sobre janela de shrinkage
    janela = y[-JANELA_SHRINK:]
    mu_j, sd_j = float(janela.mean()), float(janela.std(ddof=0))
    z = (y[-1] - mu_j) / sd_j if sd_j > 0 else 0.0

    # Iteração AR(1) a partir da âncora robusta
    y_hat = ancora
    for _ in range(h):
        y_hat = alpha + phi * y_hat

    # Shrinkage se última obs é outlier: puxa pra média da janela
    if abs(z) > THR_OUTLIER:
        y_hat = (1 - ALPHA_SHRINK) * y_hat + ALPHA_SHRINK * mu_j

    return float(y_hat), res


# ─── Pesos GR rolling (igual v1, adaptado para múltiplos fatores) ─────────
def _peso_gr_rolling(pim_var: pd.Series, F: np.ndarray,
                       fechas: pd.DatetimeIndex, h: int = 2,
                       min_treino: int = 36) -> tuple[float, int]:
    if F.ndim == 1:
        F = F.reshape(1, -1)
    n = F.shape[1]
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
        pred_dfm, _ = _previsao_dfm(F[:, : origem_idx + 1],
                                       fechas[: origem_idx + 1],
                                       pim_var.iloc[: origem_idx + 1], h)
        pred_ar1, _ = _previsao_ar1_robusto(pim_var.iloc[: origem_idx + 1], h)
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
    X = arr_dfm - arr_ar1
    Y_ = arr_y - arr_ar1
    denom = float(np.sum(X * X))
    w = (float(np.sum(X * Y_)) / denom) if denom > 0 else 0.5
    return float(np.clip(w, 0.0, 1.0)), len(alvos)


def _quantil_conformal(erros_abs: np.ndarray, alfa: float) -> float:
    n = len(erros_abs)
    if n == 0:
        return float("nan")
    k = min(int(np.ceil((n + 1) * (1 - alfa))), n)
    return float(np.sort(erros_abs)[k - 1])


def _registrar(linha: dict) -> bool:
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
        for c in COLUNAS_HIST:
            linha.setdefault(c, "")
        w.writerow(linha)
    return True


# ─── Main ─────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=None,
                        help="Data de emissão (AAAA-MM-DD). Default: hoje UTC.")
    args = parser.parse_args()

    data_emissao = args.data or datetime.utcnow().strftime("%Y-%m-%d")
    ano_emissao = int(data_emissao[:4])
    print(f"\n  ── gera_previsao_v2 — emissão {data_emissao} ──")

    print("  [1] Carregando painel ampliado (ANTAQ + macro)…")
    painel = _carregar_painel_var12m_ampliado()
    print(f"      {painel.shape[0]} meses × {painel.shape[1]} séries")

    print("  [2] Carregando PIM-PF…")
    pim_var, pim_idx = _carregar_pim_var12m_e_idx()
    print(f"      Última obs PIM-PF: {pim_var.index[-1].date()}")

    idx_comum = painel.dropna(how="any").index.intersection(pim_var.index)
    if len(idx_comum) < 36:
        raise RuntimeError("janela insuficiente.")
    origem = idx_comum.max()
    print(f"      Origem da previsão: {origem.date()}")

    print("  [3] Padronizando (sem look-ahead)…")
    z = _zscore_treino(painel, origem).loc[:origem].dropna(how="any")
    print(f"      Painel padronizado: {z.shape[0]} meses × {z.shape[1]} séries")

    print(f"  [4] DFM v2 (k_factors={K_FACTORS})…")
    payload, _ = _treinar_ou_carregar_dfm_v2(z.values, ano_emissao)
    modelo = payload["modelo_serializado"]
    k_usado = payload.get("k_factors", K_FACTORS)
    print(f"      Modelo usa k_factors = {k_usado}")

    print("  [5] Aplicando Kalman smoother…")
    F = _kalman_smoother_factor(modelo, z.values, k_factors=k_usado)
    print(f"      F shape: {F.shape}")

    print("  [6] Previsões h=1 e h=2…")
    pim_var_ate = pim_var.loc[:origem]
    pred_dfm_h2, resid_dfm_h2 = _previsao_dfm(F, z.index, pim_var_ate, h=2)
    pred_dfm_h1, _            = _previsao_dfm(F, z.index, pim_var_ate, h=1)
    pred_ar1_h2, resid_ar1_h2 = _previsao_ar1_robusto(pim_var_ate, h=2)
    pred_ar1_h1, _            = _previsao_ar1_robusto(pim_var_ate, h=1)
    print(f"      DFM h=2: {pred_dfm_h2*100:+.2f} pp · AR1r h=2: {pred_ar1_h2*100:+.2f} pp")
    print(f"      DFM h=1: {pred_dfm_h1*100:+.2f} pp · AR1r h=1: {pred_ar1_h1*100:+.2f} pp")

    print("  [7] Pesos GR rolling…")
    w_h2, n_h2 = _peso_gr_rolling(pim_var_ate, F, z.index, h=2)
    w_h1, n_h1 = _peso_gr_rolling(pim_var_ate, F, z.index, h=1)
    print(f"      h=1: w_DFM = {w_h1:.3f}  ({n_h1} origens)")
    print(f"      h=2: w_DFM = {w_h2:.3f}  ({n_h2} origens)")

    pred_comb_h2 = w_h2 * pred_dfm_h2 + (1 - w_h2) * pred_ar1_h2
    pred_comb_h1 = w_h1 * pred_dfm_h1 + (1 - w_h1) * pred_ar1_h1

    print("  [8] Intervalo conformal 80%…")
    n_erros = min(len(resid_dfm_h2), len(resid_ar1_h2))
    err_comb = (w_h2 * resid_dfm_h2[-n_erros:]
                 + (1 - w_h2) * resid_ar1_h2[-n_erros:])
    metade = max(len(err_comb) // 2, 12)
    q_h2 = _quantil_conformal(np.abs(err_comb[:metade]), ALPHA_CONF)

    err_comb1 = (w_h1 * resid_dfm_h2[-n_erros:]
                  + (1 - w_h1) * resid_ar1_h2[-n_erros:])
    q_h1 = _quantil_conformal(np.abs(err_comb1[:max(len(err_comb1)//2, 12)]),
                                 ALPHA_CONF)

    print("  [9] Registrando previsões v2 em historico_v2.csv…")
    mes_h2 = origem + pd.DateOffset(months=2)
    mes_h1 = origem + pd.DateOffset(months=1)

    for h, mes_alvo, pred, q, w in [
        (2, mes_h2, pred_comb_h2, q_h2, w_h2),
        (1, mes_h1, pred_comb_h1, q_h1, w_h1),
    ]:
        _registrar({
            "data_emissao":          data_emissao,
            "mes_alvo":              mes_alvo.strftime("%Y-%m-%d"),
            "horizonte":             h,
            "previsao_pontual":      round(pred, 6),
            "intervalo_inferior_80": round(pred - q, 6),
            "intervalo_superior_80": round(pred + q, 6),
            "peso_dfm":              round(w, 4),
            "tipo":                  "producao",
            "realizado":             "",
            "erro":                  "",
            "dentro_intervalo":      "",
            "modelo_dfm":            f"dfm_v2_{ano_emissao}",
            "ultima_obs_pim_pf":     origem.strftime("%Y-%m-%d"),
        })

    print(f"\n  ✓ Previsões v2 emitidas:")
    print(f"      h=2 → {mes_h2.date()}: var12m = {pred_comb_h2*100:+.2f} pp "
            f"(IC 80% [{(pred_comb_h2-q_h2)*100:+.2f}, {(pred_comb_h2+q_h2)*100:+.2f}])")
    print(f"      h=1 → {mes_h1.date()}: var12m = {pred_comb_h1*100:+.2f} pp "
            f"(IC 80% [{(pred_comb_h1-q_h1)*100:+.2f}, {(pred_comb_h1+q_h1)*100:+.2f}])")
    print(f"  ✓ {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
