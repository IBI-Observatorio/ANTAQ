"""
Cluster 7 — Análises Inéditas

25. ★ Fingerprint operacional de porto — clustering por ano
26. ★ Custo de Ineficiência por Tonelada — (T2+T4)×$/h / tons
27. ★ Sazonalidade latente em T1
28. ★ Análise de rede: centralidade dos portos
30. ★ PortGDP — movimentação portuária mensal como indicador
"""
from __future__ import annotations
import warnings

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from .utils import conectar, salvar, secao
from .macro import pim_pf as _pim_pf

warnings.filterwarnings("ignore", category=FutureWarning)


# ─── 25 — Fingerprint operacional ─────────────────────────────────────────────
def a25_fingerprint(top_n: int = 25, n_clusters: int = 5):
    """Cada porto é um vetor (T1, T2, T3, T4, % cont., % granel, tons) por ano.
    KMeans → cluster por ano → mostra quando portos mudaram de perfil."""
    secao(25, "★ Fingerprint operacional de porto (clustering por ano)")
    try:
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        print("  scikit-learn não disponível — pulando.")
        return None

    db = conectar()
    df = db.sql(
        f"""
        WITH portos_top AS (
          SELECT a."Porto Atracação" AS porto,
                 SUM(c.VLPesoCargaBruta) AS t
          FROM Carga c JOIN Atracacao a USING(IDAtracacao)
          WHERE c.FlagMCOperacaoCarga=1 AND c.Ano BETWEEN 2015 AND 2025
          GROUP BY 1 ORDER BY 2 DESC LIMIT {top_n}
        ),
        atr AS (
          SELECT a."Porto Atracação" AS porto, a.Ano,
                 AVG(TEsperaAtracacao)    AS T1,
                 AVG(TEsperaInicioOp)     AS T2,
                 AVG(TOperacao)           AS T3,
                 AVG(TEsperaDesatracacao) AS T4
          FROM atracacao_completa a
          WHERE a."Tipo de Operação"='Movimentação da Carga'
            AND a.TEstadia BETWEEN 0.5 AND 720
            AND a.Ano BETWEEN 2015 AND 2025
          GROUP BY 1,2
        ),
        car AS (
          SELECT a."Porto Atracação" AS porto, a.Ano,
                 SUM(c.VLPesoCargaBruta) AS ton,
                 SUM(CASE WHEN c."Natureza da Carga"='Carga Conteinerizada' THEN c.VLPesoCargaBruta ELSE 0 END) AS ton_cont,
                 SUM(CASE WHEN c."Natureza da Carga"='Granel Sólido'        THEN c.VLPesoCargaBruta ELSE 0 END) AS ton_gs,
                 SUM(CASE WHEN c."Natureza da Carga"='Granel Líquido e Gasoso' THEN c.VLPesoCargaBruta ELSE 0 END) AS ton_gl
          FROM Carga c JOIN Atracacao a USING(IDAtracacao)
          WHERE c.FlagMCOperacaoCarga=1 AND c.Ano BETWEEN 2015 AND 2025
          GROUP BY 1,2
        )
        SELECT atr.porto, atr.Ano, atr.T1, atr.T2, atr.T3, atr.T4,
               car.ton, car.ton_cont, car.ton_gs, car.ton_gl
        FROM atr JOIN car USING(porto, Ano)
        JOIN portos_top USING(porto)
        """
    ).df()
    df["pct_cont"] = df["ton_cont"]/df["ton"]
    df["pct_gs"]   = df["ton_gs"]/df["ton"]
    df["pct_gl"]   = df["ton_gl"]/df["ton"]
    feats = ["T1", "T2", "T3", "T4", "pct_cont", "pct_gs", "pct_gl"]
    X = df[feats].fillna(0).values
    Xs = StandardScaler().fit_transform(X)
    km = KMeans(n_clusters=n_clusters, n_init=10, random_state=0).fit(Xs)
    df["cluster"] = km.labels_

    pivot = df.pivot(index="porto", columns="Ano", values="cluster")
    # Detectar mudanças
    mudancas = []
    for porto, row in pivot.iterrows():
        vals = row.dropna().values
        n_unique = len(set(vals))
        if n_unique > 1:
            # ano da última mudança
            for i in range(len(vals)-1, 0, -1):
                if vals[i] != vals[i-1]:
                    mudancas.append((porto, int(row.dropna().index[i]), int(vals[i-1]), int(vals[i])))
                    break

    fig, ax = plt.subplots(figsize=(13, 8))
    cmap = plt.get_cmap("tab10", n_clusters)
    pivot_sorted = pivot.loc[pivot.notna().sum(axis=1).sort_values(ascending=False).index]
    im = ax.imshow(pivot_sorted.values, aspect="auto", cmap=cmap, interpolation="nearest")
    ax.set_yticks(range(len(pivot_sorted))); ax.set_yticklabels(pivot_sorted.index, fontsize=7)
    ax.set_xticks(range(len(pivot_sorted.columns))); ax.set_xticklabels(pivot_sorted.columns.astype(int))
    ax.set_title(f"Fingerprint operacional — {n_clusters} clusters de perfil ano-a-ano")
    cbar = plt.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
    cbar.set_label("Cluster")
    salvar(fig, "25_fingerprint")

    print(f"  Portos analisados: {len(pivot)}; clusters: {n_clusters}")
    print(f"  N portos que mudaram de cluster ao menos uma vez: {len(mudancas)}")
    if mudancas:
        for p, ano, c0, c1 in mudancas[:6]:
            print(f"    {p[:32]:32s}  {ano}  cluster {c0} → {c1}")
    # Caracterização dos clusters
    print("  Centróides (médias por cluster, escala original):")
    centro = df.groupby("cluster")[feats].mean().round(2)
    print(centro.to_string())
    return df


# ─── 26 — Custo de Ineficiência por Tonelada ──────────────────────────────────
def a26_custo_por_tonelada(custo_dia_usd: float = 25_000, brl_usd: float = 5.20):
    secao(26, "★ Custo de ineficiência por tonelada")
    db = conectar()
    df = db.sql(
        """
        SELECT a."Porto Atracação"           AS porto,
               c."Natureza da Carga"        AS natureza,
               SUM(a.TEsperaInicioOp + a.TEsperaDesatracacao) AS h_perdidas,
               SUM(c.VLPesoCargaBruta)      AS ton
        FROM atracacao_completa a JOIN Carga c USING(IDAtracacao)
        WHERE a."Tipo de Operação"='Movimentação da Carga'
          AND a.TEstadia BETWEEN 0.5 AND 720
          AND c.FlagMCOperacaoCarga=1
          AND a.Ano BETWEEN 2020 AND 2025
        GROUP BY 1,2
        HAVING SUM(c.VLPesoCargaBruta) > 1e6
        """
    ).df()
    custo_h = custo_dia_usd / 24 * brl_usd  # R$/h
    df["custo_brl_por_ton"] = df["h_perdidas"] * custo_h / df["ton"]
    pivot = df.pivot(index="porto", columns="natureza",
                     values="custo_brl_por_ton")
    # top 20 piores em granel sólido
    if "Granel Sólido" in pivot.columns:
        top = pivot["Granel Sólido"].dropna().sort_values(ascending=False).head(20)
    else:
        top = pivot.mean(axis=1).sort_values(ascending=False).head(20)

    fig, ax = plt.subplots(figsize=(11, 7))
    top.sort_values().plot(kind="barh", ax=ax, color="#c1322f")
    ax.set_xlabel("R$ / tonelada de custo de tempo perdido (T2+T4)")
    ax.set_title(f"Custo de ineficiência por tonelada — Granel Sólido (US$ {custo_dia_usd/1000:.0f}k/dia)")
    salvar(fig, "26_custo_por_tonelada")

    print("  Top 5 portos com maior custo R$/ton (Granel Sólido):")
    for p, v in top.head(5).items():
        print(f"    {p[:40]:40s}  R$ {v:6.2f}/t")
    print("  Estes portos cobram um pedágio invisível pela ineficiência.")
    # Retorna long-format (porto × natureza × custo) — front-end pode filtrar.
    return df[["porto", "natureza", "custo_brl_por_ton", "ton"]]


# ─── 27 — Sazonalidade latente em T1 ──────────────────────────────────────────
def a27_sazonalidade_t1():
    secao(27, "★ Sazonalidade latente em T1 vs ocupação")
    db = conectar()

    df = db.sql(
        """
        WITH tx AS (
          SELECT IDBerco,
                 AnoTaxaOcupacao  AS ano,
                 LOWER("MêsTaxaOcupacao") AS mes,
                 SUM(TempoEmMinutosdias)/(30.0*24*60)*100 AS ocup_pct
          FROM TaxaOcupacao
          GROUP BY 1,2,3
        ),
        atr AS (
          SELECT IDBerco,
                 EXTRACT(year  FROM "Data Atracação")::INT AS ano,
                 LOWER(CASE EXTRACT(month FROM "Data Atracação")
                   WHEN 1 THEN 'jan' WHEN 2 THEN 'fev' WHEN 3 THEN 'mar'
                   WHEN 4 THEN 'abr' WHEN 5 THEN 'mai' WHEN 6 THEN 'jun'
                   WHEN 7 THEN 'jul' WHEN 8 THEN 'ago' WHEN 9 THEN 'set'
                   WHEN 10 THEN 'out' WHEN 11 THEN 'nov' WHEN 12 THEN 'dez' END) AS mes,
                 AVG(TEsperaAtracacao) AS T1
          FROM atracacao_completa
          WHERE "Tipo de Operação"='Movimentação da Carga'
            AND TEstadia BETWEEN 0.5 AND 720 AND IDBerco IS NOT NULL
            AND "Data Atracação" >= '2020-01-01'
          GROUP BY 1,2,3
        )
        SELECT a.IDBerco, a.ano, a.mes, t.ocup_pct, a.T1
        FROM atr a JOIN tx t USING(IDBerco, ano, mes)
        WHERE t.ocup_pct > 5 AND a.T1 IS NOT NULL
        """
    ).df()

    meses_pt = {"jan":1,"fev":2,"mar":3,"abr":4,"mai":5,"jun":6,
                "jul":7,"ago":8,"set":9,"out":10,"nov":11,"dez":12}
    df["mes_n"] = df["mes"].map(meses_pt)

    saz = df.groupby("mes_n").agg(T1=("T1", "median"), ocup=("ocup_pct", "median"))
    saz["T1_norm"]   = saz["T1"]   / saz["T1"].mean()
    saz["ocup_norm"] = saz["ocup"] / saz["ocup"].mean()
    delta = (saz["T1_norm"] - saz["ocup_norm"])

    fig, ax = plt.subplots()
    ax.plot(saz.index, saz["T1_norm"]*100, marker="o", color="#c1322f", lw=2, label="T1 (índice mensal)")
    ax.plot(saz.index, saz["ocup_norm"]*100, marker="s", color="#3a64a8", lw=2, label="Ocupação (índice mensal)")
    ax.axhline(100, color="grey", lw=0.6)
    ax.set_xticks(range(1, 13))
    ax.set_ylabel("Índice mensal (média = 100)")
    ax.set_title("Sazonalidade — T1 sobe sem ocupação subir = gargalo no canal")
    ax.legend(framealpha=0.9)
    salvar(fig, "27_sazonalidade_t1")

    pico_t1 = saz["T1_norm"].idxmax(); pico_oc = saz["ocup_norm"].idxmax()
    print(f"  Pico de T1 mensal: mês {pico_t1}  ({saz.loc[pico_t1,'T1_norm']:.2f}× média)")
    print(f"  Pico de ocupação:  mês {pico_oc}  ({saz.loc[pico_oc,'ocup_norm']:.2f}× média)")
    descolamento = delta.abs().max()
    print(f"  Maior descolamento T1-ocupação: mês {delta.abs().idxmax()}  ({descolamento*100:.0f}p.p.)")
    if pico_t1 != pico_oc and descolamento > 0.10:
        print("  → Sazonalidade do T1 NÃO acompanha ocupação — gargalo provável é canal/atracação, não berço.")
    else:
        print("  → T1 e ocupação se movem juntos — gargalo no berço.")
    return saz


# ─── 28 — Centralidade da rede portuária ──────────────────────────────────────
def a28_centralidade_rede(top_n_print: int = 12):
    secao(28, "★ Centralidade dos portos na rede de cabotagem")
    db = conectar()

    df = db.sql(
        """
        SELECT o."Origem Nome"   AS origem,
               d."Nome Destino"  AS destino,
               SUM(c.VLPesoCargaBruta) AS ton,
               SUM(c.TEU)              AS teus
        FROM Carga c
        JOIN InstalacaoOrigem  o ON c.Origem  = o.Origem
        JOIN InstalacaoDestino d ON c.Destino = d.Destino
        WHERE c.FlagCabotagem = 1
          AND c.Ano BETWEEN 2022 AND 2024
          AND o."Origem Nome" <> d."Nome Destino"
          AND o."Origem Nome" IS NOT NULL AND d."Nome Destino" IS NOT NULL
        GROUP BY 1,2
        HAVING SUM(c.VLPesoCargaBruta) > 1000
        """
    ).df()

    try:
        import networkx as nx
    except ImportError:
        print("  networkx não disponível — pulando.")
        return None

    G = nx.DiGraph()
    for _, r in df.iterrows():
        G.add_edge(r.origem, r.destino, weight=float(r.ton))

    # Centralities
    btw = nx.betweenness_centrality(G, weight=None)
    deg_in  = dict(G.in_degree())
    deg_out = dict(G.out_degree())
    # eigenvector centrality precisa de grafo conexo: usa a maior componente fracamente conexa
    largest = max(nx.weakly_connected_components(G), key=len)
    Gc = G.subgraph(largest).copy()
    try:
        eig = nx.eigenvector_centrality_numpy(Gc)
    except Exception:
        eig = nx.pagerank(G)
    eig = {n: eig.get(n, 0.0) for n in G.nodes}

    cent = pd.DataFrame({
        "betweenness": btw,
        "in_degree":   deg_in,
        "out_degree":  deg_out,
        "eigen":       eig,
    }).sort_values("betweenness", ascending=False)
    cent.index.name = "porto"

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    top_b = cent.head(top_n_print)
    axes[0].barh(top_b.index[::-1], top_b["betweenness"][::-1], color="#3a64a8")
    axes[0].set_title("Top portos por betweenness (pontos únicos de falha)")
    axes[0].set_xlabel("Betweenness centrality")

    top_e = cent.sort_values("eigen", ascending=False).head(top_n_print)
    axes[1].barh(top_e.index[::-1], top_e["eigen"][::-1], color="#7fb069")
    axes[1].set_title("Top portos por eigenvector (importância de rede)")
    axes[1].set_xlabel("Eigenvector centrality")
    salvar(fig, "28_centralidade")

    print(f"  Nós (portos): {G.number_of_nodes()}; arestas (rotas): {G.number_of_edges()}")
    print(f"  Top 5 por betweenness (gargalos da rede):")
    for p, b in cent["betweenness"].head(5).items():
        print(f"    {p[:40]:40s}  {b:.4f}")
    return cent


# ─── 30 — PortGDP ─────────────────────────────────────────────────────────────
def a30_portgdp():
    """PortGDP × PIM-PF (Produção Industrial Mensal IBGE, dessazonalizada).
    Testa correlação contemporânea e com defasagens 1-3 meses."""
    secao(30, "PIM-PF Combinado IBI — componente DFM em horizonte bimestral")
    db = conectar()
    df = db.sql(
        """
        SELECT date_trunc('month', a."Data Atracação")::DATE AS mes,
               -- Variante 1: tudo (movimentação industrial total)
               SUM(CASE WHEN c.FlagMCOperacaoCarga=1
                         AND c."Natureza da Carga" IN
                              ('Carga Conteinerizada','Carga Geral','Granel Líquido e Gasoso')
                        THEN c.VLPesoCargaBruta ELSE 0 END) AS ton_total,
               -- Variante 2: só importações industriais (insumos → produção)
               SUM(CASE WHEN c.FlagLongoCurso=1
                         AND c.Sentido='Desembarcados'
                         AND c."Natureza da Carga" IN
                              ('Carga Conteinerizada','Carga Geral','Granel Líquido e Gasoso')
                        THEN c.VLPesoCargaBruta ELSE 0 END) AS ton_imp
        FROM Carga c JOIN Atracacao a USING(IDAtracacao)
        WHERE a."Data Atracação" >= '2014-01-01' AND a."Data Atracação" < '2026-01-01'
        GROUP BY 1 ORDER BY 1
        """
    ).df().set_index("mes")
    df.index = pd.to_datetime(df.index)

    def dessaz_idx(s: pd.Series) -> pd.Series:
        sazonal = s / s.rolling(12, center=True).mean()
        ds = s / sazonal.groupby(sazonal.index.month).transform("mean")
        return ds / ds.loc["2014-01":"2014-12"].mean() * 100

    portgdp_idx = dessaz_idx(df["ton_total"])
    portgdp_imp = dessaz_idx(df["ton_imp"])

    # PIM-PF do BCB SGS 28503 (via analises.macro)
    try:
        pim = _pim_pf()
    except Exception as e:
        print(f"  ✗ Falha ao obter PIM-PF ({e}); rodando só o lado portuário.")
        pim = None

    fig, axes = plt.subplots(2, 1, figsize=(12, 9))

    # Painel 1 — séries no mesmo eixo (índices base 2014 = 100)
    ax = axes[0]
    ax.plot(portgdp_idx.index, portgdp_idx.values, color="#3a64a8", lw=1.8,
            label="PortGDP — total industrial")
    ax.plot(portgdp_imp.index, portgdp_imp.values, color="#7fb069", lw=1.8,
            label="PortGDP — só importações de insumos")
    if pim is not None:
        pim_idx = pim / pim.loc["2014-01":"2014-12"].mean() * 100
        ax.plot(pim_idx.index, pim_idx.values, color="#c1322f", lw=1.8,
                label="PIM-PF Indústria Geral (IBGE)")
    ax.axhline(100, color="grey", lw=0.6, ls="--")
    ax.axvspan(pd.Timestamp("2020-03-01"), pd.Timestamp("2020-09-01"), alpha=0.10, color="grey")
    ax.set_ylabel("Índice (média 2014 = 100, dessaz)")
    ax.set_title("PortGDP × PIM-PF — Indústria Geral (IBGE/BCB SGS 28503)")
    ax.legend(framealpha=0.9, fontsize=9)

    # Painel 2 — correlação cruzada (ambas variantes)
    ax2 = axes[1]
    resultados = {}
    if pim is not None:
        pim_norm = pim / pim.loc["2014-01":"2014-12"].mean() * 100
        v_pim    = pim_norm.pct_change(12)
        lags = list(range(-6, 7))
        for nome, serie, cor in [("Total", portgdp_idx, "#3a64a8"),
                                 ("Importações", portgdp_imp, "#7fb069")]:
            v_p = serie.pct_change(12)
            corr_s = pd.Series({L: v_p.shift(L).corr(v_pim) for L in lags})
            resultados[nome] = corr_s
        x = np.arange(len(lags)); w = 0.4
        ax2.bar(x - w/2, resultados["Total"].values,       w, color="#3a64a8", label="PortGDP Total")
        ax2.bar(x + w/2, resultados["Importações"].values, w, color="#7fb069", label="PortGDP Importações")
        ax2.set_xticks(x); ax2.set_xticklabels(lags)
        ax2.axhline(0, color="black", lw=0.6)
        ax2.set_xlabel("Lag em meses — negativo: PortGDP antecede PIM-PF")
        ax2.set_ylabel("Correlação (variação 12m)")
        # melhor lag para importações
        melhor_imp = resultados["Importações"].abs().idxmax()
        ax2.set_title(f"Correlação cruzada (var. 12m) — pico importações em lag {melhor_imp:+d}m  "
                      f"(corr {resultados['Importações'][melhor_imp]:+.2f})")
        ax2.legend(framealpha=0.9, fontsize=9)
    else:
        ax2.text(0.5, 0.5, "PIM-PF indisponível", ha="center", va="center", transform=ax2.transAxes)
    salvar(fig, "30_portgdp")

    cresc = (portgdp_idx.tail(12).mean() / portgdp_idx.head(12).mean() - 1)
    cresc_i = (portgdp_imp.tail(12).mean() / portgdp_imp.head(12).mean() - 1)
    print(f"  PortGDP total       2014→{portgdp_idx.index[-1].year}: {cresc:+.0%}")
    print(f"  PortGDP importações 2014→{portgdp_imp.index[-1].year}: {cresc_i:+.0%}")

    if pim is None:
        return pd.DataFrame({"portgdp_total": portgdp_idx, "portgdp_imp": portgdp_imp})

    # Resumo das correlações (logging)
    for nome, corr_s in resultados.items():
        melhor = corr_s.abs().idxmax()
        print(f"\n  {nome}: melhor lag {melhor:+d}m, corr {corr_s[melhor]:+.2f}")

    # ─── DataFrame de séries históricas ──────────────────────────────────────
    # NOTA: o forecast univariado simples do v1 foi REMOVIDO. A previsão
    # oficial pública vem do pipeline pipelines/pimpf_combinado/ (modelo
    # combinado AR(1)+DFM com pesos GR rolling, Linha D), entregue via
    # bloco card_previsao_atual lido de data/previsoes/historico.csv.
    pim_idx_full = pim / pim.loc["2014-01":"2014-12"].mean() * 100
    out = pd.DataFrame({
        "portgdp_total": portgdp_idx,
        "portgdp_imp":   portgdp_imp,
        "pim_pf":        pim_idx_full.reindex(portgdp_idx.index),
    }).sort_index()
    out.index.name = "mes"

    # ─── Achados editoriais removidos ───────────────────────────────────────
    # A seção "Achados" foi suprimida por decisão editorial: o conteúdo
    # essencial está reproduzido nos blocos visuais dedicados — Card de
    # previsão atual, Track record, Disclaimer vintage e Bloco de
    # transparência. Manter um achados=[] vazio garante que o componente
    # IndicadorPage não renderize a seção "Achados" (condicional já
    # verifica achados?.length > 0).
    achados = []

    # ─── Blocos estruturados extras (renderizados pelo componente React) ──
    # Card de previsão atual, track record, métricas em produção e
    # disclaimer de vintage vêm do pipeline oficial em
    # pipelines/pimpf_combinado/, não da função aqui.
    extras = _construir_extras_card_pim_pf()

    resultado = {
        "df": out.reset_index(),
        "achados": achados,
    }
    resultado.update(extras)
    return resultado


def _construir_extras_card_pim_pf() -> dict:
    """
    Lê data/previsoes/historico.csv (se existir) e produz blocos
    estruturados que o componente IndicadorPage renderiza:
      - card_previsao_atual
      - track_record
      - disclaimer_vintage
    Se o histórico não existir, retorna apenas o disclaimer.
    """
    import pandas as pd
    from pathlib import Path

    hist_path = (Path(__file__).resolve().parent.parent
                  / "data" / "previsoes" / "historico.csv")

    extras = {
        "disclaimer_vintage": (
            "Validação realizada em série revisada do PIM-PF (BCB SGS 28503). "
            "Performance em previsão real, contra primeiro vintage publicado "
            "pelo IBGE, pode degradar 10–25% conforme literatura padrão de "
            "nowcasting macroeconômico. Snapshots de cada release do PIM-PF "
            "e da ANTAQ são arquivados desde mai/2026 para análise comparativa "
            "de degradação por revisão, a ser publicada na re-validação de "
            "mai/2028."
        ),
    }

    if not hist_path.exists():
        return extras

    df = pd.read_csv(hist_path, parse_dates=["mes_alvo", "data_emissao"])
    df = df.sort_values(["mes_alvo", "data_emissao"])

    # ── Card de previsão atual (última de produção sem realizado) ──
    aberta = df[(df["tipo"] == "producao") &
                  (df["realizado"].isna() | (df["realizado"] == ""))]
    if len(aberta) > 0:
        # h=2 publicada se houver, senão h=1
        aberta = aberta.sort_values(["horizonte"], ascending=False)
        atual = aberta.iloc[0]
        extras["card_previsao_atual"] = {
            "mes_alvo":              atual["mes_alvo"].strftime("%Y-%m"),
            "horizonte":             int(atual["horizonte"]),
            "var12m_prevista_pp":    float(atual["previsao_pontual"]) * 100,
            "intervalo_inferior_pp": float(atual["intervalo_inferior_80"]) * 100,
            "intervalo_superior_pp": float(atual["intervalo_superior_80"]) * 100,
            "peso_dfm":              float(atual["peso_dfm"])
                                       if pd.notna(atual["peso_dfm"]) else None,
            "ultima_obs_pim_pf":     str(atual["ultima_obs_pim_pf"]),
            "data_emissao":          atual["data_emissao"].strftime("%Y-%m-%d"),
            "modelo_dfm":            str(atual["modelo_dfm"]),
        }

    # ── Track record das últimas 12 (qualquer tipo) ──
    ultimas = df.tail(12).copy()
    track = []
    for _, r in ultimas.iterrows():
        realizado_pp = (float(r["realizado"]) * 100
                          if pd.notna(r["realizado"]) and r["realizado"] != ""
                          else None)
        erro_pp = (float(r["erro"]) * 100
                    if pd.notna(r["erro"]) and r["erro"] != ""
                    else None)
        dentro = r["dentro_intervalo"]
        if isinstance(dentro, str):
            dentro = dentro.lower() in ("true", "1")
        elif pd.isna(dentro):
            dentro = None
        track.append({
            "mes_alvo":         r["mes_alvo"].strftime("%Y-%m"),
            "horizonte":        int(r["horizonte"]),
            "previsto_pp":      float(r["previsao_pontual"]) * 100,
            "realizado_pp":     realizado_pp,
            "erro_abs_pp":      erro_pp,
            "dentro_intervalo": dentro,
            "tipo":             str(r["tipo"]),
        })
    extras["track_record"] = track

    # ── Métricas em produção (só se houver ≥ 6 com realizado) ──
    prod = df[(df["tipo"] == "producao") &
                df["realizado"].notna() & (df["realizado"] != "")]
    n_prod_realizadas = len(prod)
    if n_prod_realizadas >= 6:
        prod = prod.copy()
        prod["realizado"] = pd.to_numeric(prod["realizado"])
        prod["erro"] = pd.to_numeric(prod["erro"])
        prod["dentro_intervalo"] = prod["dentro_intervalo"].astype(str) \
            .str.lower().map({"true": True, "false": False}).fillna(False)
        extras["metricas_producao"] = {
            "n_previsoes": int(n_prod_realizadas),
            "mae_total_pp":     float(prod["erro"].mean()) * 100,
            "mae_rolling_12m_pp": float(prod["erro"].tail(12).mean()) * 100,
            "cobertura_empirica": float(prod["dentro_intervalo"].mean()),
            "mae_validacao_historica_pp": 3.01,  # referência fixa (linha D)
            "primeira_previsao_alvo": prod["mes_alvo"].min().strftime("%Y-%m"),
            "ultima_previsao_alvo":   prod["mes_alvo"].max().strftime("%Y-%m"),
        }
    else:
        extras["metricas_producao"] = {
            "n_previsoes": int(n_prod_realizadas),
            "mensagem": (f"Aguardando 6 previsões com realizado para reportar "
                         f"métricas em produção (atual: {n_prod_realizadas})."),
            "mae_validacao_historica_pp": 3.01,
        }

    return extras


def main():
    a25_fingerprint()
    a26_custo_por_tonelada()
    a27_sazonalidade_t1()
    a28_centralidade_rede()
    a30_portgdp()


if __name__ == "__main__":
    main()
