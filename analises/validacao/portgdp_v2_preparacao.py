"""
Dia 1.3 — Tratamento das 35 séries do dicionário PortGDP v2.

Pipeline:
    1. Imputação linear de NaNs isolados (≤2 meses consecutivos).
       Maiores → série excluída no passo anterior; aqui é redundante.
    2. Dessazonalização individual (componente saz removido):
       - tenta X-13 ARIMA-SEATS (se binário disponível);
       - fallback documentado em STL (`statsmodels.tsa.STL`).
    3. var12m (variação interanual = pct_change(12)).

Outputs:
    validacao/portgdp_v2/series_tratadas.parquet
    validacao/portgdp_v2/dessaz_metodo.csv
"""
from __future__ import annotations

import sys
from pathlib import Path
import warnings

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "validacao" / "portgdp_v2"

warnings.filterwarnings("ignore")


def _tentar_x13(serie: pd.Series) -> tuple[pd.Series | None, str]:
    """Retorna (série dessaz, método_usado) ou (None, motivo_falha)."""
    try:
        from statsmodels.tsa.x13 import x13_arima_analysis
        res = x13_arima_analysis(serie.dropna(), x12path=None,
                                  outlier=True, trading=False)
        return res.seasadj.reindex(serie.index), "x13"
    except Exception as e:
        return None, f"x13_falhou: {type(e).__name__}"


def _stl_dessaz(serie: pd.Series) -> pd.Series:
    """Fallback STL — robusto, sem binário externo."""
    from statsmodels.tsa.seasonal import STL
    s = serie.copy()
    # STL não aceita NaN; interpola brevemente para o ajuste
    s_imp = s.interpolate(method="linear", limit_direction="both")
    stl = STL(s_imp, period=12, robust=True).fit()
    dessaz = s_imp - stl.seasonal
    # Preserva NaN onde o original tinha NaN
    dessaz[s.isna()] = np.nan
    return dessaz


def imputar_isolados(serie: pd.Series) -> pd.Series:
    """Interpola NaN isolados (gap ≤2 meses) por interpolação linear."""
    s = serie.copy()
    nan_mask = s.isna()
    # Localiza gaps e seu comprimento
    grupos = (nan_mask != nan_mask.shift()).cumsum()
    for g, idx_grupo in nan_mask.groupby(grupos):
        if not idx_grupo.iloc[0]:
            continue
        if len(idx_grupo) <= 2:
            indices = idx_grupo.index
            s.loc[indices] = np.nan  # mantém para interpolar abaixo
    return s.interpolate(method="linear", limit=2, limit_direction="both")


def main() -> int:
    print("\n  ── Dia 1.3 — Tratamento das séries ──")
    dic = pd.read_csv(OUT / "dicionario_series.csv")
    dic_ok = dic[~dic["excluida"]].copy()
    chaves_ok = dic_ok["chave"].tolist()
    print(f"    {len(chaves_ok)} séries a tratar.")

    painel = pd.read_parquet(OUT / "series_brutas.parquet").set_index("mes")
    painel.index = pd.to_datetime(painel.index)
    painel = painel[chaves_ok]

    print("\n  [1] Imputação linear de NaN isolados (≤2 meses)…")
    painel_imp = painel.apply(imputar_isolados, axis=0)

    print("\n  [2] Dessazonalização (X-13 → fallback STL)…")
    metodos = []
    dessaz = pd.DataFrame(index=painel_imp.index)
    for chave in painel_imp.columns:
        s = painel_imp[chave]
        # Tenta X-13. Em ambiente sem binário (típico Windows), vai falhar logo.
        d, metodo = _tentar_x13(s)
        if d is None:
            d = _stl_dessaz(s)
            metodo = "stl"
        dessaz[chave] = d
        metodos.append({"chave": chave, "metodo": metodo})
    df_metodos = pd.DataFrame(metodos)
    df_metodos.to_csv(OUT / "dessaz_metodo.csv", index=False)
    print(f"    Métodos usados: "
          f"{df_metodos['metodo'].value_counts().to_dict()}")

    print("\n  [3] var12m (pct_change(12))…")
    var12m = dessaz.pct_change(12)

    # Salva
    painel_final = pd.concat([
        dessaz.add_prefix("dessaz__"),
        var12m.add_prefix("var12m__"),
    ], axis=1)
    arq = OUT / "series_tratadas.parquet"
    painel_final.reset_index().to_parquet(arq)
    print(f"\n  ✓ {arq.relative_to(ROOT)}")
    print(f"    {painel_final.shape[1]} colunas (dessaz__ + var12m__) × "
          f"{painel_final.shape[0]} meses")

    # Sanity: var12m disponível a partir de 2015-01
    n_var12m_ok = int(var12m.dropna(how="all").shape[0])
    print(f"    var12m disponível em {n_var12m_ok} meses "
          f"(esperado ~{painel_final.shape[0] - 12}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
