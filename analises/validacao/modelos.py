"""
Modelos uniformes para o exercício walk-forward — cada um expõe a interface:

    fit_predict(train_y, train_x, h, quantiles) -> dict[str, float]

onde:
    train_y  — Series com a variação interanual do PIM-PF, índice temporal
    train_x  — Series com a variação interanual do PortGDP-Importações
    h        — horizonte (1 ou 2)
    quantiles — lista de níveis em (0, 1)

A função retorna um dict {f"q{ll:02d}": valor, "media": valor} contendo os
quantis preditos para o ponto-alvo (uma única observação, h passos à frente
do último ponto de train_y).

Convenção temporal:
    train_y é a série até a origem τ inclusive.
    A função prevê y_{τ+h}.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

QUANTIS_DEFAULT = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90]


def _quantis_de_residuos(ponto: float, residuos: np.ndarray,
                          niveis: list[float]) -> dict:
    """
    Aproximação não-paramétrica: assume distribuição preditiva =
    ponto + quantis empíricos dos resíduos in-sample.
    """
    if len(residuos) == 0 or not np.all(np.isfinite(residuos)):
        return {f"q{int(q*100):02d}": ponto for q in niveis} | {"media": ponto}
    q_resid = np.quantile(residuos, niveis)
    return ({f"q{int(q*100):02d}": float(ponto + q_resid[i])
             for i, q in enumerate(niveis)}
            | {"media": float(ponto)})


# ─── Modelo 1: PortGDP OLS (alvo da validação) ────────────────────────────────
def portgdp_ols(train_y: pd.Series, train_x: pd.Series, h: int,
                lag: int = 2, quantiles: list[float] = QUANTIS_DEFAULT) -> dict:
    """
    y_t = α + β · x_{t-lag}
    Para prever y_{τ+h}, usa x_{τ+h-lag}, observado em t = τ + h - lag.
    Como h ≤ lag, o feature está dentro do treino.
    """
    if h > lag:
        raise ValueError(f"OLS univariado não cobre h={h} > lag={lag} sem feature futura.")

    # Pares (y_t, x_{t-lag}) com t-lag ≥ início e t ≤ fim do treino
    y_aligned = train_y.iloc[lag:]
    x_aligned = train_x.iloc[:len(train_x) - lag]
    pares = pd.concat([y_aligned.reset_index(drop=True).rename("y"),
                       x_aligned.reset_index(drop=True).rename("x")],
                      axis=1).dropna()
    if len(pares) < 5:
        return {f"q{int(q*100):02d}": np.nan for q in quantiles} | {"media": np.nan}

    slope, intercept = np.polyfit(pares["x"], pares["y"], 1)

    # Feature para previsão de y_{τ+h}: x_{τ+h-lag}
    # Em índices da série: último ponto de train_x é τ; precisamos do índice (τ+h-lag).
    # Off-by-one: se τ é a última posição de train_x (idx = len-1), então
    # τ+h-lag = len-1 + h - lag (valor negativo se h < lag).
    pos_feature = len(train_x) - 1 + h - lag
    if pos_feature < 0 or pos_feature >= len(train_x):
        return {f"q{int(q*100):02d}": np.nan for q in quantiles} | {"media": np.nan}
    x_alvo = float(train_x.iloc[pos_feature])
    if not np.isfinite(x_alvo):
        return {f"q{int(q*100):02d}": np.nan for q in quantiles} | {"media": np.nan}

    ponto = slope * x_alvo + intercept
    residuos = pares["y"].values - (slope * pares["x"].values + intercept)
    return _quantis_de_residuos(ponto, residuos, quantiles)


# ─── Modelo 2: Random Walk (na variação) ──────────────────────────────────────
def random_walk(train_y: pd.Series, train_x: pd.Series, h: int,
                quantiles: list[float] = QUANTIS_DEFAULT) -> dict:
    """
    y_{τ+h} = y_τ + ε

    Variância dos resíduos in-sample escalada por √h para horizonte > 1
    (sob i.i.d., var(y_{τ+h} - y_τ) = h·σ²).
    """
    if len(train_y) < 2:
        return {f"q{int(q*100):02d}": np.nan for q in quantiles} | {"media": np.nan}
    ponto = float(train_y.iloc[-1])
    diffs = train_y.diff().dropna().values
    # Para horizonte h, soma de h passos i.i.d. → escala √h
    quantis = np.quantile(diffs, quantiles) * np.sqrt(h)
    return ({f"q{int(q*100):02d}": float(ponto + quantis[i])
             for i, q in enumerate(quantiles)}
            | {"media": ponto})


# ─── Modelo 3: Sazonal Naive ──────────────────────────────────────────────────
def sazonal_naive(train_y: pd.Series, train_x: pd.Series, h: int,
                  quantiles: list[float] = QUANTIS_DEFAULT) -> dict:
    """
    y_{τ+h} = y_{τ+h-12}

    Resíduos: erros do mesmo modelo aplicado in-sample.
    """
    if len(train_y) < 13:
        return {f"q{int(q*100):02d}": np.nan for q in quantiles} | {"media": np.nan}
    pos_alvo = len(train_y) - 1 + h
    pos_base = pos_alvo - 12
    if pos_base < 0 or pos_base >= len(train_y):
        return {f"q{int(q*100):02d}": np.nan for q in quantiles} | {"media": np.nan}
    ponto = float(train_y.iloc[pos_base])
    # Resíduos in-sample do mesmo modelo
    y = train_y.values
    if len(y) <= 12:
        residuos = np.array([])
    else:
        residuos = y[12:] - y[:-12]
    return _quantis_de_residuos(ponto, residuos, quantiles)


# ─── Modelo 4: AR(1) ──────────────────────────────────────────────────────────
def ar1(train_y: pd.Series, train_x: pd.Series, h: int,
        quantiles: list[float] = QUANTIS_DEFAULT) -> dict:
    """
    y_t = α + φ · y_{t-1} + ε

    Forecast iterativo h passos à frente.
    Para múltiplos passos, escala dos resíduos é √(Σ φ^{2k}, k=0..h-1)
    (variância da soma de inovações descontadas por φ).
    """
    y = train_y.dropna().values
    if len(y) < 5:
        return {f"q{int(q*100):02d}": np.nan for q in quantiles} | {"media": np.nan}
    Y, X = y[1:], y[:-1]
    phi, alpha = np.polyfit(X, Y, 1)
    # Forecast iterativo
    y_hat = float(y[-1])
    for _ in range(h):
        y_hat = alpha + phi * y_hat
    # Resíduos 1-passo in-sample
    residuos_1 = Y - (alpha + phi * X)
    # Escala para horizonte h
    if abs(phi) < 1:
        scale_h = float(np.sqrt(sum(phi ** (2 * k) for k in range(h))))
    else:
        scale_h = float(np.sqrt(h))
    quantis = np.quantile(residuos_1, quantiles) * scale_h
    return ({f"q{int(q*100):02d}": float(y_hat + quantis[i])
             for i, q in enumerate(quantiles)}
            | {"media": y_hat})


# ─── Modelo 5: ARDL com dummy COVID + interação ────────────────────────────
COVID_INI = pd.Timestamp("2020-03-01")
COVID_FIM = pd.Timestamp("2021-12-01")


def _dummy_covid(idx: pd.DatetimeIndex) -> np.ndarray:
    """Vetor 1/0 para o período COVID (mar/2020 a dez/2021)."""
    arr = (idx >= COVID_INI) & (idx <= COVID_FIM)
    if hasattr(arr, "values"):
        arr = arr.values
    return np.asarray(arr, dtype=float)


def ardl(train_y: pd.Series, train_x: pd.Series, h: int,
         p: int = 1, lag_x: int = 2,
         quantiles: list[float] = QUANTIS_DEFAULT) -> dict:
    """
    ARDL(p, lag_x):
        y_t = α + Σ_{i=1..p} φ_i · y_{t-i}
                + β · x_{t-lag_x}
                + γ · D_covid_t
                + δ · D_covid_t · x_{t-lag_x}
                + ε_t

    Para prever y_{τ+h} com h ≤ lag_x:
        - Componente AR é iterado se h > 1.
        - Feature x_{τ+h-lag_x} já é observada (h ≤ lag_x).
        - D_covid_{τ+h} é determinístico.

    Resíduos in-sample (1-passo) escalados por √h para horizonte > 1
    (aproximação ingênua; conformal seria mais correto, ver item 3 do plano).
    """
    if h > lag_x:
        raise ValueError(f"ARDL: h={h} > lag_x={lag_x} requer feature futura.")
    y = train_y.dropna()
    x = train_x.reindex(y.index)
    if len(y) < max(p, lag_x) + 10:
        return {f"q{int(q*100):02d}": np.nan for q in quantiles} | {"media": np.nan}

    n = len(y)
    inicio = max(p, lag_x)
    Y = y.iloc[inicio:].values
    # Construção da matriz X
    cols = []
    cols_nomes = []
    for i in range(1, p + 1):
        cols.append(y.iloc[inicio - i : n - i].values)
        cols_nomes.append(f"y_lag{i}")
    cols.append(x.iloc[inicio - lag_x : n - lag_x].values)
    cols_nomes.append("x_lag")
    d_full = _dummy_covid(y.index)
    cols.append(d_full[inicio:])
    cols_nomes.append("d_covid")
    cols.append(d_full[inicio:] * cols[-2])  # interação D · x_lag
    cols_nomes.append("d_x_lag")
    X = np.column_stack(cols)

    # Filtra linhas válidas
    mask = np.all(np.isfinite(X), axis=1) & np.isfinite(Y)
    if mask.sum() < 10:
        return {f"q{int(q*100):02d}": np.nan for q in quantiles} | {"media": np.nan}
    X, Y = X[mask], Y[mask]

    # OLS via lstsq + intercepto
    X1 = np.column_stack([np.ones(len(X)), X])
    coef, *_ = np.linalg.lstsq(X1, Y, rcond=None)
    fitted = X1 @ coef
    residuos = Y - fitted

    # ─── Forecast iterativo ─────────────────────────────────────────────────
    alpha = coef[0]
    phi = coef[1 : 1 + p]
    beta = coef[1 + p]
    gamma = coef[2 + p]
    delta = coef[3 + p]

    # Histórico de y mais recente (precisa dos últimos p valores)
    y_hist = list(y.iloc[-p:].values)
    pos_x_target_global = n - 1 + h - lag_x   # índice em x para y_{τ+h}
    if pos_x_target_global < 0 or pos_x_target_global >= len(x):
        return {f"q{int(q*100):02d}": np.nan for q in quantiles} | {"media": np.nan}

    # Para h passos, iteramos. A feature x_{t-lag_x} para forecast no passo k
    # corresponde ao índice (n - 1 + k - lag_x) em x.
    y_pred = None
    for k in range(1, h + 1):
        pos_x_k = n - 1 + k - lag_x
        if pos_x_k < 0 or pos_x_k >= len(x):
            return {f"q{int(q*100):02d}": np.nan for q in quantiles} | {"media": np.nan}
        x_k = float(x.iloc[pos_x_k])
        if not np.isfinite(x_k):
            return {f"q{int(q*100):02d}": np.nan for q in quantiles} | {"media": np.nan}
        # D_covid no mês alvo: t = τ + k. Aproximação: usa o índice de y se
        # extensível, ou 0 se o mês alvo está fora do índice de treino.
        # Como τ+k > último mês de y, D_covid_{τ+k} = 0 no momento do lançamento
        # (todos os meses pós-treino estão depois de COVID_FIM).
        d_k = 0.0
        ar_part = sum(phi[i] * y_hist[-(i + 1)] for i in range(p))
        y_pred = alpha + ar_part + beta * x_k + gamma * d_k + delta * d_k * x_k
        y_hist.append(y_pred)

    # Escala dos resíduos para horizonte h (aproximação √h)
    quantis = np.quantile(residuos, quantiles) * np.sqrt(h)
    return ({f"q{int(q*100):02d}": float(y_pred + quantis[i])
             for i, q in enumerate(quantiles)}
            | {"media": float(y_pred)})


# ─── Modelos de combinação (ensemble) ──────────────────────────────────────
def _combinar(componentes: list[dict], operacao: str) -> dict:
    """Combina dicts {q##: valor} via mediana ou média componente-a-componente."""
    chaves = componentes[0].keys()
    out = {}
    for k in chaves:
        valores = [c.get(k, np.nan) for c in componentes]
        valores = [v for v in valores if v is not None and np.isfinite(v)]
        if not valores:
            out[k] = np.nan
        elif operacao == "mediana":
            out[k] = float(np.median(valores))
        elif operacao == "media":
            out[k] = float(np.mean(valores))
        else:
            raise ValueError(operacao)
    return out


def ensemble_mediana(*previsoes_dict: dict) -> dict:
    """Mediana componente-a-componente de N previsões (cada uma é um dict de quantis)."""
    return _combinar(list(previsoes_dict), "mediana")


def ensemble_media(*previsoes_dict: dict) -> dict:
    """Média componente-a-componente de N previsões."""
    return _combinar(list(previsoes_dict), "media")


MODELOS: dict[str, callable] = {
    "portgdp_ols": portgdp_ols,
    "rw":          random_walk,
    "sazonal_naive": sazonal_naive,
    "ar1":         ar1,
    "ardl":        ardl,
}
