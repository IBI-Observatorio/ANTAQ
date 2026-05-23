"""
Exporta os dados consolidados das análises de médias móveis para JSON,
prontos para o dashboard Next.js (puxa via raw.githubusercontent.com com ISR).

Saída: data/dashboard/*.json

    python -m analises.exportar_json

Arquivos gerados:
    meta.json              — metadados (última atualização, período coberto)
    kpis.json              — números do topo do dashboard
    series_mensais.json    — todas as séries mensais (long format)
    momentum.json          — momentum (a/a MA12) + Δ6m por natureza
    stl.json               — decomposição STL por natureza
    granel_liquido.json    — decomposição do crescimento do líquido por bucket
    rotas.json             — top 30 rotas TEU cabotagem
    portos.json            — diagnóstico de divergência porto vs natureza
    forecast.json          — modelo + previsão do momentum Conteinerizada
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import STL
from sklearn.linear_model import LinearRegression

import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import antaq
from analises.macro import ibc_br

OUT = ROOT / "data" / "dashboard"
OUT.mkdir(parents=True, exist_ok=True)

ANO_INICIO = 2010
JANELA = 12

NATUREZAS = ["Granel Sólido", "Granel Líquido e Gasoso",
             "Carga Geral", "Carga Conteinerizada"]

SLUG = {
    "Granel Sólido":           "granel_solido",
    "Granel Líquido e Gasoso": "granel_liquido",
    "Carga Geral":             "carga_geral",
    "Carga Conteinerizada":    "conteinerizada",
    "Cabotagem":               "cabotagem",
    "Longo Curso":             "longo_curso",
    "Embarcados":              "embarque",
    "Desembarcados":           "desembarque",
    "Cabotagem doméstica":     "cabotagem_domestica",
    "Offshore (FPSO/ZEE)":     "offshore",
}


def _r(x, casas=2):
    """Arredonda e converte NaN→None para JSON limpo."""
    if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
        return None
    return round(float(x), casas)


def _ym(ts):
    """Timestamp → 'YYYY-MM' string."""
    return pd.Timestamp(ts).strftime("%Y-%m")


def _dump(obj, nome):
    path = OUT / f"{nome}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    tam_kb = path.stat().st_size / 1024
    print(f"  ✓ {nome}.json  ({tam_kb:>6.1f} KB)")
    return path


# ─── Helpers comuns ──────────────────────────────────────────────────────────
def _serie_naturezas(db) -> pd.DataFrame:
    df = db.sql(
        f"""
        SELECT date_trunc('month', a."Data Atracação")::DATE AS data,
               c."Natureza da Carga"                         AS natureza,
               SUM(c.VLPesoCargaBruta)                       AS toneladas
        FROM Carga c JOIN Atracacao a USING (IDAtracacao)
        WHERE c.FlagMCOperacaoCarga = 1
          AND a."Data Atracação" IS NOT NULL
          AND a.Ano >= {ANO_INICIO}
          AND EXTRACT(year FROM a."Data Atracação") >= {ANO_INICIO}
        GROUP BY 1, 2 ORDER BY 1, 2
        """
    ).df()
    df["data"] = pd.to_datetime(df["data"])
    wide = (df.pivot(index="data", columns="natureza", values="toneladas")
              .sort_index().asfreq("MS"))
    # descarta último mês se parcial
    soma_recente = wide.tail(13).head(12).sum(axis=1).mean()
    if wide.tail(1).sum(axis=1).iloc[0] < 0.5 * soma_recente:
        wide = wide.iloc[:-1]
    return wide


# ─── 1. Séries mensais consolidadas (long format) ────────────────────────────
def gerar_series_mensais(db) -> tuple[pd.Timestamp, dict]:
    """
    Retorna long format com todas as séries mensais usadas no dashboard.
    Cada linha: {data, serie_id, serie_label, grupo, mensal_mt, ma12_mt, sum12_mt, yoy_ma_pct, yoy_sum_pct}
    """
    out = []

    # (a) Por natureza
    wide = _serie_naturezas(db)
    for nat in NATUREZAS:
        if nat not in wide.columns:
            continue
        s = wide[nat]
        ma = s.rolling(JANELA, min_periods=JANELA).mean()
        sum12 = s.rolling(12, min_periods=12).sum()
        yoy_ma = ma.pct_change(12) * 100
        yoy_sum = sum12.pct_change(12) * 100
        for d in s.index:
            out.append({
                "data": _ym(d),
                "serie": f"natureza:{SLUG[nat]}",
                "label": nat,
                "grupo": "natureza",
                "mensal_mt":   _r(s.loc[d] / 1e6),
                "ma12_mt":     _r(ma.loc[d] / 1e6),
                "sum12_mt":    _r(sum12.loc[d] / 1e6, 1),
                "yoy_ma_pct":  _r(yoy_ma.loc[d]),
                "yoy_sum_pct": _r(yoy_sum.loc[d]),
            })

    # (b) Cabotagem doméstica vs offshore
    cab = db.sql(
        f"""
        SELECT date_trunc('month', a."Data Atracação")::DATE AS data,
               CASE WHEN c.FlagOffshore = 1 THEN 'Offshore (FPSO/ZEE)'
                    ELSE 'Cabotagem doméstica' END             AS categoria,
               SUM(c.VLPesoCargaBruta) AS toneladas
        FROM Carga c JOIN Atracacao a USING (IDAtracacao)
        WHERE c.FlagMCOperacaoCarga = 1
          AND c."Tipo Navegação" = 'Cabotagem'
          AND a."Data Atracação" IS NOT NULL
          AND a.Ano >= {ANO_INICIO}
          AND EXTRACT(year FROM a."Data Atracação") >= {ANO_INICIO}
        GROUP BY 1,2 ORDER BY 1,2
        """
    ).df()
    cab["data"] = pd.to_datetime(cab["data"])
    cab_wide = (cab.pivot(index="data", columns="categoria", values="toneladas")
                  .sort_index().asfreq("MS").fillna(0))
    soma_recente = cab_wide.tail(13).head(12).sum(axis=1).mean()
    if cab_wide.tail(1).sum(axis=1).iloc[0] < 0.5 * soma_recente:
        cab_wide = cab_wide.iloc[:-1]
    for cat in cab_wide.columns:
        s = cab_wide[cat]
        ma = s.rolling(JANELA, min_periods=JANELA).mean()
        sum12 = s.rolling(12, min_periods=12).sum()
        yoy_ma = ma.pct_change(12) * 100
        yoy_sum = sum12.pct_change(12) * 100
        for d in s.index:
            out.append({
                "data": _ym(d),
                "serie": f"cabotagem:{SLUG.get(cat, cat)}",
                "label": cat,
                "grupo": "cabotagem",
                "mensal_mt":   _r(s.loc[d] / 1e6),
                "ma12_mt":     _r(ma.loc[d] / 1e6),
                "sum12_mt":    _r(sum12.loc[d] / 1e6, 1),
                "yoy_ma_pct":  _r(yoy_ma.loc[d]),
                "yoy_sum_pct": _r(yoy_sum.loc[d]),
            })

    # (c) Total por navegação (Cabotagem vs Longo Curso) — toneladas
    nav = db.sql(
        f"""
        SELECT date_trunc('month', a."Data Atracação")::DATE AS data,
               c."Tipo Navegação"                            AS navegacao,
               SUM(c.VLPesoCargaBruta)                       AS toneladas
        FROM Carga c JOIN Atracacao a USING (IDAtracacao)
        WHERE c.FlagMCOperacaoCarga = 1
          AND c."Tipo Navegação" IN ('Cabotagem','Longo Curso')
          AND a."Data Atracação" IS NOT NULL
          AND a.Ano >= {ANO_INICIO}
          AND EXTRACT(year FROM a."Data Atracação") >= {ANO_INICIO}
        GROUP BY 1,2 ORDER BY 1,2
        """
    ).df()
    nav["data"] = pd.to_datetime(nav["data"])
    nav_w = (nav.pivot(index="data", columns="navegacao", values="toneladas")
                .sort_index().asfreq("MS").fillna(0))
    soma_recente = nav_w.tail(13).head(12).sum(axis=1).mean()
    if nav_w.tail(1).sum(axis=1).iloc[0] < 0.5 * soma_recente:
        nav_w = nav_w.iloc[:-1]
    for n in nav_w.columns:
        s = nav_w[n]
        ma = s.rolling(JANELA, min_periods=JANELA).mean()
        sum12 = s.rolling(12, min_periods=12).sum()
        yoy_ma = ma.pct_change(12) * 100
        yoy_sum = sum12.pct_change(12) * 100
        for d in s.index:
            out.append({
                "data": _ym(d),
                "serie": f"navegacao:{SLUG[n]}",
                "label": n,
                "grupo": "navegacao",
                "mensal_mt":   _r(s.loc[d] / 1e6),
                "ma12_mt":     _r(ma.loc[d] / 1e6),
                "sum12_mt":    _r(sum12.loc[d] / 1e6, 1),
                "yoy_ma_pct":  _r(yoy_ma.loc[d]),
                "yoy_sum_pct": _r(yoy_sum.loc[d]),
            })

    # (d) TEU por navegação
    teu = db.sql(
        f"""
        SELECT date_trunc('month', a."Data Atracação")::DATE AS data,
               c."Tipo Navegação"                            AS navegacao,
               SUM(c.TEU)                                     AS teu
        FROM Carga c JOIN Atracacao a USING (IDAtracacao)
        WHERE c.FlagMCOperacaoCarga = 1
          AND c."Natureza da Carga" = 'Carga Conteinerizada'
          AND c.TEU > 0
          AND c."Tipo Navegação" IN ('Cabotagem','Longo Curso')
          AND a."Data Atracação" IS NOT NULL
          AND a.Ano >= {ANO_INICIO}
          AND EXTRACT(year FROM a."Data Atracação") >= {ANO_INICIO}
        GROUP BY 1,2 ORDER BY 1,2
        """
    ).df()
    teu["data"] = pd.to_datetime(teu["data"])
    teu_w = (teu.pivot(index="data", columns="navegacao", values="teu")
                .sort_index().asfreq("MS").fillna(0))
    soma_recente = teu_w.tail(13).head(12).sum(axis=1).mean()
    if teu_w.tail(1).sum(axis=1).iloc[0] < 0.5 * soma_recente:
        teu_w = teu_w.iloc[:-1]
    for n in teu_w.columns:
        s = teu_w[n]
        ma = s.rolling(JANELA, min_periods=JANELA).mean()
        sum12 = s.rolling(12, min_periods=12).sum()
        yoy_ma = ma.pct_change(12) * 100
        yoy_sum = sum12.pct_change(12) * 100
        for d in s.index:
            out.append({
                "data": _ym(d),
                "serie": f"teu:{SLUG[n]}",
                "label": f"{n} (TEU)",
                "grupo": "teu",
                "mensal_teu":   _r(s.loc[d], 0),
                "ma12_teu":     _r(ma.loc[d], 0),
                "sum12_teu":    _r(sum12.loc[d], 0),
                "yoy_ma_pct":   _r(yoy_ma.loc[d]),
                "yoy_sum_pct":  _r(yoy_sum.loc[d]),
            })

    # (e) Longo Curso por sentido (exportação/importação)
    lc = db.sql(
        f"""
        SELECT date_trunc('month', a."Data Atracação")::DATE AS data,
               c.Sentido                                     AS sentido,
               SUM(c.VLPesoCargaBruta)                       AS toneladas
        FROM Carga c JOIN Atracacao a USING (IDAtracacao)
        WHERE c.FlagMCOperacaoCarga = 1
          AND c."Tipo Navegação" = 'Longo Curso'
          AND c.Sentido IN ('Embarcados','Desembarcados')
          AND a."Data Atracação" IS NOT NULL
          AND a.Ano >= {ANO_INICIO}
          AND EXTRACT(year FROM a."Data Atracação") >= {ANO_INICIO}
        GROUP BY 1,2 ORDER BY 1,2
        """
    ).df()
    lc["data"] = pd.to_datetime(lc["data"])
    lc_w = (lc.pivot(index="data", columns="sentido", values="toneladas")
              .sort_index().asfreq("MS").fillna(0))
    soma_recente = lc_w.tail(13).head(12).sum(axis=1).mean()
    if lc_w.tail(1).sum(axis=1).iloc[0] < 0.5 * soma_recente:
        lc_w = lc_w.iloc[:-1]
    for sent in lc_w.columns:
        s = lc_w[sent]
        ma = s.rolling(JANELA, min_periods=JANELA).mean()
        sum12 = s.rolling(12, min_periods=12).sum()
        yoy_sum = sum12.pct_change(12) * 100
        for d in s.index:
            out.append({
                "data": _ym(d),
                "serie": f"lc_sentido:{SLUG[sent]}",
                "label": "Exportação" if sent == "Embarcados" else "Importação",
                "grupo": "lc_sentido",
                "mensal_mt":   _r(s.loc[d] / 1e6),
                "ma12_mt":     _r(ma.loc[d] / 1e6),
                "sum12_mt":    _r(sum12.loc[d] / 1e6, 1),
                "yoy_sum_pct": _r(yoy_sum.loc[d]),
            })

    ultimo_mes = max(pd.to_datetime(r["data"], format="%Y-%m") for r in out)
    return ultimo_mes, out


# ─── 2. KPIs do topo do dashboard ────────────────────────────────────────────
def gerar_kpis(db) -> dict:
    wide = _serie_naturezas(db)
    total = wide.sum(axis=1)
    sum12 = total.rolling(12, min_periods=12).sum()
    yoy_sum = sum12.pct_change(12) * 100
    ult_data = sum12.dropna().index[-1]

    # composição do último ponto da soma 12m
    sum12_nat = wide.rolling(12, min_periods=12).sum()
    ult_comp = sum12_nat.dropna().iloc[-1]

    # cabotagem doméstica vs offshore (último ano rolante)
    cab = db.sql(
        f"""
        SELECT CASE WHEN c.FlagOffshore = 1 THEN 'offshore' ELSE 'domestica' END AS k,
               SUM(c.VLPesoCargaBruta) AS t
        FROM Carga c JOIN Atracacao a USING (IDAtracacao)
        WHERE c.FlagMCOperacaoCarga = 1
          AND c."Tipo Navegação" = 'Cabotagem'
          AND a."Data Atracação" >= ((SELECT MAX(a2."Data Atracação") FROM Atracacao a2)
                                      - INTERVAL '12 months')
          AND a."Data Atracação" < (SELECT MAX(a2."Data Atracação") FROM Atracacao a2)
        GROUP BY 1
        """
    ).df().set_index("k")["t"]
    cab_dom = cab.get("domestica", 0.0)
    cab_off = cab.get("offshore", 0.0)
    cab_tot = cab_dom + cab_off
    pct_off = cab_off / cab_tot * 100 if cab_tot else 0

    # TEU últimos 12 meses
    teu_total = db.sql(
        f"""
        SELECT SUM(c.TEU) AS teu
        FROM Carga c JOIN Atracacao a USING (IDAtracacao)
        WHERE c.FlagMCOperacaoCarga = 1
          AND c."Natureza da Carga" = 'Carga Conteinerizada'
          AND c.TEU > 0
          AND a."Data Atracação" >= ((SELECT MAX(a2."Data Atracação") FROM Atracacao a2)
                                      - INTERVAL '12 months')
          AND a."Data Atracação" < (SELECT MAX(a2."Data Atracação") FROM Atracacao a2)
        """
    ).df().iloc[0, 0]

    # variação a/a de cada natureza (último ponto MA12)
    ma = wide.rolling(JANELA, min_periods=JANELA).mean()
    yoy_ma = ma.pct_change(12) * 100
    momentum = {SLUG[n]: _r(yoy_ma[n].dropna().iloc[-1]) for n in NATUREZAS
                if n in yoy_ma.columns}

    return {
        "referencia": _ym(ult_data),
        "total_12m_mt":     _r(sum12.loc[ult_data] / 1e6, 0),
        "total_yoy_pct":    _r(yoy_sum.loc[ult_data]),
        "cabotagem_total_mt":   _r(cab_tot / 1e6, 0),
        "cabotagem_offshore_pct": _r(pct_off, 1),
        "teu_12m":          _r(teu_total, 0),
        "composicao_12m": {SLUG[n]: _r(ult_comp[n] / 1e6, 0)
                           for n in NATUREZAS if n in ult_comp.index},
        "momentum_atual": momentum,
    }


# ─── 3. Momentum (a/a MA12 + Δ6m) por natureza ────────────────────────────────
def gerar_momentum(db) -> list:
    wide = _serie_naturezas(db)
    ma = wide.rolling(JANELA, min_periods=JANELA).mean()
    yoy_ma = ma.pct_change(12) * 100
    delta6 = yoy_ma - yoy_ma.shift(6)
    out = []
    for nat in NATUREZAS:
        if nat not in yoy_ma.columns:
            continue
        for d in yoy_ma.index:
            out.append({
                "data": _ym(d),
                "natureza": SLUG[nat],
                "yoy_ma": _r(yoy_ma[nat].loc[d]),
                "delta6": _r(delta6[nat].loc[d]),
            })
    return out


# ─── 4. STL por natureza ─────────────────────────────────────────────────────
def gerar_stl(db) -> list:
    wide = _serie_naturezas(db)
    out = []
    for nat in NATUREZAS:
        if nat not in wide.columns:
            continue
        s = wide[nat].dropna() / 1e6
        if len(s) < 24:
            continue
        stl = STL(s, period=12, robust=True).fit()
        for d in s.index:
            out.append({
                "data": _ym(d),
                "natureza": SLUG[nat],
                "observado": _r(s.loc[d]),
                "trend": _r(stl.trend.loc[d]),
                "seasonal": _r(stl.seasonal.loc[d]),
                "resid": _r(stl.resid.loc[d]),
            })
    return out


# ─── 5. Granel líquido — decomposição do crescimento ─────────────────────────
def gerar_granel_liquido(db) -> dict:
    df = db.sql(
        f"""
        SELECT date_trunc('month', a."Data Atracação")::DATE AS data,
               CASE
                 WHEN c.FlagOffshore = 1 THEN 'offshore'
                 WHEN c."Tipo Navegação" = 'Longo Curso' AND c.Sentido = 'Embarcados' THEN 'lc_exportacao'
                 WHEN c."Tipo Navegação" = 'Longo Curso' AND c.Sentido = 'Desembarcados' THEN 'lc_importacao'
                 WHEN c."Tipo Navegação" = 'Cabotagem' THEN 'cabotagem_domestica'
                 ELSE 'outros' END AS bucket,
               SUM(c.VLPesoCargaBruta) AS toneladas
        FROM Carga c JOIN Atracacao a USING (IDAtracacao)
        WHERE c.FlagMCOperacaoCarga = 1
          AND c."Natureza da Carga" = 'Granel Líquido e Gasoso'
          AND a."Data Atracação" IS NOT NULL
          AND a.Ano >= {ANO_INICIO}
          AND EXTRACT(year FROM a."Data Atracação") >= {ANO_INICIO}
        GROUP BY 1,2 ORDER BY 1,2
        """
    ).df()
    df["data"] = pd.to_datetime(df["data"])
    wide = (df.pivot(index="data", columns="bucket", values="toneladas")
              .sort_index().asfreq("MS").fillna(0))
    soma_recente = wide.tail(13).head(12).sum(axis=1).mean()
    if wide.tail(1).sum(axis=1).iloc[0] < 0.5 * soma_recente:
        wide = wide.iloc[:-1]

    ma = wide.rolling(JANELA, min_periods=JANELA).mean()
    total_t_12 = ma.sum(axis=1).shift(12)
    contrib = ma.diff(12).divide(total_t_12, axis=0) * 100
    yoy_ma = ma.pct_change(12) * 100

    series = []
    for bucket in wide.columns:
        for d in ma.index:
            series.append({
                "data": _ym(d),
                "bucket": bucket,
                "ma12_mt": _r(ma[bucket].loc[d] / 1e6),
                "contrib_pp": _r(contrib[bucket].loc[d]),
                "yoy_ma_pct": _r(yoy_ma[bucket].loc[d]),
            })

    ult = contrib.dropna(how="all").iloc[-1]
    snapshot = {b: _r(ult[b]) for b in ult.index}
    snapshot["total_yoy_pct"] = _r((ma.sum(axis=1).pct_change(12) * 100)
                                    .dropna().iloc[-1])
    snapshot["data"] = _ym(contrib.dropna(how="all").index[-1])

    return {"snapshot": snapshot, "series": series}


# ─── 6. Top rotas TEU cabotagem ──────────────────────────────────────────────
def gerar_rotas(db, top_n: int = 30) -> list:
    df = db.sql(
        f"""
        SELECT EXTRACT(year FROM a."Data Atracação")::INT AS ano,
               o."Origem Nome"  AS origem,
               o."UF.Origem"    AS uf_origem,
               d."Nome Destino" AS destino,
               d."UF.Destino"   AS uf_destino,
               SUM(c.TEU)       AS teu
        FROM Carga c JOIN Atracacao a USING (IDAtracacao)
        LEFT JOIN InstalacaoOrigem  o ON c.Origem  = o.Origem
        LEFT JOIN InstalacaoDestino d ON c.Destino = d.Destino
        WHERE c.FlagMCOperacaoCarga = 1
          AND c."Natureza da Carga" = 'Carga Conteinerizada'
          AND c."Tipo Navegação"    = 'Cabotagem'
          AND c.TEU > 0
          AND a."Data Atracação" IS NOT NULL
          AND a.Ano >= {ANO_INICIO}
          AND EXTRACT(year FROM a."Data Atracação") >= {ANO_INICIO}
        GROUP BY 1,2,3,4,5
        """
    ).df()
    # exclui ano corrente (parcial)
    ult_ano = df["ano"].max()
    df_fechado = df[df["ano"] < ult_ano]

    totais = (df.groupby(["origem", "uf_origem", "destino", "uf_destino"])
                ["teu"].sum().reset_index()
                .sort_values("teu", ascending=False).head(top_n))

    rotas = []
    for _, r in totais.iterrows():
        sub = df_fechado[(df_fechado["origem"] == r["origem"])
                          & (df_fechado["destino"] == r["destino"])]
        s = sub.groupby("ano")["teu"].sum().sort_index()
        cagr = None
        if len(s) >= 2 and s.iloc[0] > 0:
            anos = s.index[-1] - s.index[0]
            cagr = ((s.iloc[-1] / s.iloc[0]) ** (1 / anos) - 1) * 100
        rotas.append({
            "rank": len(rotas) + 1,
            "origem": r["origem"], "uf_origem": r["uf_origem"],
            "destino": r["destino"], "uf_destino": r["uf_destino"],
            "teu_acumulado": _r(r["teu"], 0),
            "teu_ultimo_ano": _r(s.iloc[-1], 0) if not s.empty else None,
            "cagr_pct": _r(cagr),
            "rota_label": f"{r['origem']} ({r['uf_origem']}) → {r['destino']} ({r['uf_destino']})",
        })
    return rotas


# ─── 7. Diagnóstico portos ───────────────────────────────────────────────────
def gerar_portos(db, top_n: int = 10) -> dict:
    df = db.sql(
        f"""
        SELECT EXTRACT(year FROM a."Data Atracação")::INT AS ano,
               a."Porto Atracação"                        AS porto,
               a.SGUF                                     AS uf,
               c."Natureza da Carga"                      AS natureza,
               SUM(c.VLPesoCargaBruta)                    AS toneladas
        FROM Carga c JOIN Atracacao a USING (IDAtracacao)
        WHERE c.FlagMCOperacaoCarga = 1
          AND a."Data Atracação" IS NOT NULL
          AND a.Ano >= 2018
          AND EXTRACT(year FROM a."Data Atracação") >= 2018
        GROUP BY 1,2,3,4
        """
    ).df()
    ult_ano = df["ano"].max()
    df = df[df["ano"] < ult_ano]
    ult_ano = df["ano"].max()
    ano_base = df["ano"].min()
    n_anos = ult_ano - ano_base

    pivot = df.pivot_table(index=["porto", "uf", "natureza"], columns="ano",
                            values="toneladas", aggfunc="sum").fillna(0)
    pivot["cagr"] = ((pivot[ult_ano] / pivot[ano_base].replace(0, np.nan))
                       ** (1 / n_anos) - 1) * 100
    pivot["ult_mt"] = pivot[ult_ano] / 1e6
    pivot = pivot.reset_index()

    nat_total = df.groupby(["natureza", "ano"])["toneladas"].sum().unstack("ano")
    nat_cagr = ((nat_total[ult_ano] / nat_total[ano_base])
                  ** (1 / n_anos) - 1) * 100
    pivot["cagr_natureza"] = pivot["natureza"].map(nat_cagr)
    pivot["divergencia"] = pivot["cagr"] - pivot["cagr_natureza"]

    relevantes = pivot[(pivot["ult_mt"] >= 0.5) & pivot["cagr"].notna()]

    portos_por_nat = {}
    for nat in NATUREZAS:
        sub = relevantes[relevantes["natureza"] == nat].sort_values("divergencia")
        if sub.empty:
            continue
        ganhadores = sub.tail(top_n).iloc[::-1]
        perdedores = sub.head(top_n)
        portos_por_nat[SLUG[nat]] = {
            "natureza_label": nat,
            "cagr_natureza_pct": _r(nat_cagr.get(nat)),
            "periodo": f"{ano_base}-{ult_ano}",
            "ganhadores": [
                {"porto": r["porto"], "uf": r["uf"],
                 "cagr_pct": _r(r["cagr"]),
                 "volume_mt": _r(r["ult_mt"], 1),
                 "divergencia_pp": _r(r["divergencia"])}
                for _, r in ganhadores.iterrows()
            ],
            "perdedores": [
                {"porto": r["porto"], "uf": r["uf"],
                 "cagr_pct": _r(r["cagr"]),
                 "volume_mt": _r(r["ult_mt"], 1),
                 "divergencia_pp": _r(r["divergencia"])}
                for _, r in perdedores.iterrows()
            ],
        }
    return {"periodo_base": f"{ano_base}-{ult_ano}", "naturezas": portos_por_nat}


# ─── 8. Forecast Conteinerizada ──────────────────────────────────────────────
def gerar_forecast(db) -> dict:
    wide = _serie_naturezas(db)
    ma = wide.rolling(JANELA, min_periods=JANELA).mean()
    mom = ma.pct_change(12) * 100
    ibc = ibc_br().resample("MS").last()
    ibc_yoy = ibc.pct_change(12) * 100

    df_full = pd.concat({
        "y": mom["Carga Conteinerizada"],
        "x_ibc": ibc_yoy.shift(5),
        "x_cg":  mom["Carga Geral"].shift(12),
    }, axis=1).dropna()

    corte = pd.Timestamp("2022-12")
    treino = df_full[df_full.index <= corte]
    teste  = df_full[df_full.index >  corte]
    model = LinearRegression().fit(treino[["x_ibc","x_cg"]].values,
                                    treino["y"].values)
    pred_in  = model.predict(treino[["x_ibc","x_cg"]].values)
    pred_oos = model.predict(teste[["x_ibc","x_cg"]].values) if len(teste) else np.array([])
    rmse_in  = float(np.sqrt(((treino["y"] - pred_in) ** 2).mean()))
    rmse_oos = float(np.sqrt(((teste["y"]  - pred_oos) ** 2).mean())) if len(teste) else None
    r2_in   = float(model.score(treino[["x_ibc","x_cg"]].values, treino["y"].values))
    r2_oos  = float(model.score(teste[["x_ibc","x_cg"]].values,  teste["y"].values)) if len(teste) > 2 else None
    corr_oos = float(np.corrcoef(teste["y"], pred_oos)[0, 1]) if len(teste) > 2 else None

    # forecast à frente
    def _months_between(a, b):
        return (a.year - b.year) * 12 + (a.month - b.month)
    ult_y      = mom["Carga Conteinerizada"].dropna().index.max()
    ult_ibc_y  = ibc_yoy.dropna().index.max()
    ult_mom_cg = mom["Carga Geral"].dropna().index.max()
    horizonte = min(
        _months_between(ult_ibc_y  + pd.DateOffset(months=5),  ult_y),
        _months_between(ult_mom_cg + pd.DateOffset(months=12), ult_y),
        12,
    )
    forecast = []
    if horizonte > 0:
        futuro = pd.date_range(ult_y + pd.DateOffset(months=1),
                                 periods=horizonte, freq="MS")
        for d in futuro:
            x_ibc_v = ibc_yoy.get(d - pd.DateOffset(months=5))
            x_cg_v  = mom["Carga Geral"].get(d - pd.DateOffset(months=12))
            if pd.isna(x_ibc_v) or pd.isna(x_cg_v):
                continue
            central = float(model.predict([[x_ibc_v, x_cg_v]])[0])
            erro = rmse_oos if rmse_oos else rmse_in
            forecast.append({
                "data": _ym(d),
                "central_pct": _r(central),
                "low_pct":  _r(central - erro),
                "high_pct": _r(central + erro),
            })

    # série modelo (treino + oos) para overlay
    serie_modelo = []
    for d, p in zip(treino.index, pred_in):
        serie_modelo.append({"data": _ym(d), "predito": _r(float(p)),
                              "observado": _r(float(treino["y"].loc[d])),
                              "fase": "treino"})
    for d, p in zip(teste.index, pred_oos):
        serie_modelo.append({"data": _ym(d), "predito": _r(float(p)),
                              "observado": _r(float(teste["y"].loc[d])),
                              "fase": "oos"})

    return {
        "modelo": {
            "spec": "momentum_conteiner(t) = a + b·IBC-Br_yoy(t-5) + c·momentum_cargageral(t-12)",
            "corte_treino": _ym(corte),
            "coef_ibc": _r(float(model.coef_[0]), 3),
            "coef_carga_geral": _r(float(model.coef_[1]), 3),
            "intercept": _r(float(model.intercept_), 3),
            "r2_in_sample": _r(r2_in, 3),
            "r2_oos": _r(r2_oos, 3) if r2_oos is not None else None,
            "rmse_in_pp": _r(rmse_in),
            "rmse_oos_pp": _r(rmse_oos) if rmse_oos else None,
            "corr_oos": _r(corr_oos, 3) if corr_oos else None,
        },
        "serie": serie_modelo,
        "forecast": forecast,
    }


# ─── Main ────────────────────────────────────────────────────────────────────
def main():
    print(f"Exportando para {OUT}\n")
    db = antaq.conectar()

    ultimo_mes, series = gerar_series_mensais(db)
    _dump(series, "series_mensais")

    _dump(gerar_kpis(db), "kpis")
    _dump(gerar_momentum(db), "momentum")
    _dump(gerar_stl(db), "stl")
    _dump(gerar_granel_liquido(db), "granel_liquido")
    _dump(gerar_rotas(db), "rotas")
    _dump(gerar_portos(db), "portos")
    _dump(gerar_forecast(db), "forecast")

    meta = {
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ultimo_mes_dados": _ym(ultimo_mes),
        "fonte": "ANTAQ — Base Estatística Aquaviária",
        "filtro": "FlagMCOperacaoCarga = 1 (evita dupla contagem cabotagem)",
        "janela_ma": JANELA,
        "ano_inicio": ANO_INICIO,
        "arquivos": [
            "meta", "kpis", "series_mensais", "momentum", "stl",
            "granel_liquido", "rotas", "portos", "forecast",
        ],
    }
    _dump(meta, "meta")

    total_kb = sum((OUT / f"{n}.json").stat().st_size
                   for n in meta["arquivos"]) / 1024
    print(f"\nTotal: {total_kb:,.1f} KB em {OUT}")
    print(f"Última observação na base: {meta['ultimo_mes_dados']}")


if __name__ == "__main__":
    main()
