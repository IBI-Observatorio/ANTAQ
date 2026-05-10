"""
Cluster 2 — Contêineres

06. Índice de desequilíbrio cheio/vazio por corredor
07. Cheio/Vazio como proxy de câmbio
08. Conteúdo real dos contêineres (NCM SH4) — industrialização vs commoditização
09. Vazio estrutural vs sazonal
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from .utils import conectar, salvar, secao
from .macro import usdbrl_anual, usdbrl_mensal


# ─── 06 — Cheio/Vazio por corredor ────────────────────────────────────────────
def a06_desequilibrio_cheio_vazio(top_corredores: int = 12):
    """Rota = porto BR ↔ continente; razão Cheio/Vazio = competitividade exportadora."""
    secao(6, "Cheio/Vazio por corredor (proxy de competitividade)")
    db = conectar()

    df = db.sql(
        f"""
        SELECT a."Porto Atracação"     AS porto_br,
               COALESCE(o."Continente Origem", d."Continente Destino") AS continente_externo,
               c.Sentido,
               c.ConteinerEstado       AS estado,
               COUNT(*)                AS movs
        FROM Carga c JOIN Atracacao a USING(IDAtracacao)
        LEFT JOIN InstalacaoOrigem  o ON c.Origem  = o.Origem
        LEFT JOIN InstalacaoDestino d ON c.Destino = d.Destino
        WHERE c."Natureza da Carga" = 'Carga Conteinerizada'
          AND c.FlagLongoCurso = 1
          AND c.Ano BETWEEN 2018 AND 2025
          AND estado IN ('Cheio','Vazio')
        GROUP BY 1,2,3,4
        """
    ).df()

    g = (df.groupby(["porto_br", "continente_externo", "Sentido", "estado"])["movs"]
            .sum().unstack("estado").fillna(0))
    g["razao"] = (g["Cheio"] / g["Vazio"]).replace([np.inf, -np.inf], np.nan)
    g["movs_total"] = g["Cheio"] + g["Vazio"]
    g = g.reset_index()

    emb = (g.query("Sentido=='Embarcados'")
             .sort_values("movs_total", ascending=False)
             .head(top_corredores))

    fig, ax = plt.subplots(figsize=(11, 6))
    cores = ["#7fb069" if r > 1 else "#d94747" for r in emb["razao"]]
    labels = emb["porto_br"].str[:20] + " → " + emb["continente_externo"].str[:18]
    ax.barh(labels, emb["razao"], color=cores)
    ax.axvline(1, color="grey", lw=1, ls="--")
    ax.set_xlabel("Cheios embarcados / Vazios embarcados")
    ax.set_title("Desequilíbrio cheio/vazio nas exportações por corredor (2018-25)")
    ax.invert_yaxis()
    salvar(fig, "06_desequilibrio_cheio_vazio")

    fortes  = emb.query("razao > 1.5").head(3)
    fracos  = emb.query("razao < 0.7").head(3)
    print(f"  Razão média Cheio/Vazio embarcados (top {top_corredores} corredores): {emb['razao'].mean():.2f}")
    if not fortes.empty:
        print(f"  Mais exportador: {fortes.iloc[0].porto_br} → {fortes.iloc[0].continente_externo} ({fortes.iloc[0].razao:.2f})")
    if not fracos.empty:
        print(f"  Mais 'devolve vazio': {fracos.iloc[0].porto_br} → {fracos.iloc[0].continente_externo} ({fracos.iloc[0].razao:.2f})")
    print(f"  Razão >1 = exporta mais cheios; <1 = recebe cheios e devolve vazios.")
    return g


# ─── 07 — Cheio/Vazio como proxy de câmbio ────────────────────────────────────
def a07_proxy_cambio():
    secao(7, "Cheio/Vazio anual × câmbio BRL/USD")
    db = conectar()
    df = db.sql(
        """
        SELECT c.Ano,
               c.Sentido,
               SUM(CASE WHEN c.ConteinerEstado='Cheio' THEN 1 ELSE 0 END) AS cheio,
               SUM(CASE WHEN c.ConteinerEstado='Vazio' THEN 1 ELSE 0 END) AS vazio
        FROM Carga c
        WHERE c."Natureza da Carga" = 'Carga Conteinerizada'
          AND c.FlagLongoCurso = 1
          AND c.Ano BETWEEN 2010 AND 2025
        GROUP BY 1,2
        """
    ).df()
    pivot = df.pivot(index="Ano", columns="Sentido",
                     values=["cheio", "vazio"]).fillna(0)
    razao_emb = pivot[("cheio", "Embarcados")] / pivot[("vazio", "Embarcados")]
    razao_des = pivot[("cheio", "Desembarcados")] / pivot[("vazio", "Desembarcados")]
    cambio = usdbrl_anual().reindex(razao_emb.index)

    corr_emb = razao_emb.corr(cambio)
    corr_des = razao_des.corr(cambio)
    corr_emb_lag = razao_emb.shift(-1).corr(cambio)  # câmbio atual prediz razão t+1?

    fig, ax = plt.subplots()
    ax.plot(razao_emb.index, razao_emb.values, lw=2, color="#7fb069", label="Cheio/Vazio embarcados")
    ax.plot(razao_des.index, razao_des.values, lw=2, color="#d94747", label="Cheio/Vazio desembarcados")
    ax.set_ylabel("Razão Cheio/Vazio")
    ax2 = ax.twinx()
    ax2.plot(cambio.index, cambio.values, color="grey", ls="--", label="USD/BRL")
    ax2.set_ylabel("R$/US$")
    ax2.grid(False)
    ax.set_title(f"Razão Cheio/Vazio × Câmbio  (corr embarc.={corr_emb:+.2f}, lag1={corr_emb_lag:+.2f})")
    fig.legend(loc="upper center", ncols=3, bbox_to_anchor=(0.5, 0.97), frameon=False, fontsize=9)
    salvar(fig, "07_cheio_vazio_vs_cambio")

    print(f"  Correlação embarcados × USD/BRL contemporâneo: {corr_emb:+.2f}")
    print(f"  Correlação desembarcados × USD/BRL:            {corr_des:+.2f}")
    print(f"  Correlação embarcados × USD/BRL com lag 1 ano: {corr_emb_lag:+.2f}")
    print(f"  Câmbio alto (real fraco) → mais cheios embarcados (exportação) e menos desembarcados.")
    return pd.DataFrame({"Cheio_Vazio_emb": razao_emb,
                         "Cheio_Vazio_des": razao_des,
                         "USDBRL": cambio})


# ─── 08 — Conteúdo real dos contêineres (NCM) ─────────────────────────────────
def a08_conteudo_conteineres():
    """Industrialização vs commoditização da pauta conteinerizada."""
    secao(8, "Conteúdo real dos contêineres (NCM SH4)")
    db = conectar()

    # 144M linhas — agregamos antes de descer ao pandas.
    df = db.sql(
        """
        SELECT cc.Ano,
               mc."Grupo Mercadoria Conteinerizada" AS grupo,
               c.Sentido,
               SUM(cc.VLPesoCargaConteinerizada)    AS toneladas
        FROM CargaConteinerizada cc
        JOIN Carga c USING(IDCarga)
        LEFT JOIN MercadoriaConteinerizada mc
               ON cc.CDMercadoriaConteinerizada = mc.CDMercadoriaConteinerizada
        WHERE c.FlagLongoCurso = 1
          AND cc.Ano BETWEEN 2010 AND 2025
        GROUP BY 1,2,3
        """
    ).df()

    df["grupo"] = df["grupo"].fillna("Não classificado")
    emb = df[df["Sentido"] == "Embarcados"]
    pivot = (emb.groupby(["Ano", "grupo"])["toneladas"].sum()
                .unstack("grupo").fillna(0))
    pct = pivot.div(pivot.sum(axis=1), axis=0)
    top10_grupos = pct.mean().sort_values(ascending=False).head(10).index.tolist()
    pct_top = pct[top10_grupos]

    fig, ax = plt.subplots(figsize=(12, 6))
    pct_top.plot.area(ax=ax, cmap="tab20", lw=0)
    ax.set_ylim(0, pct_top.sum(axis=1).max() * 1.02)
    ax.set_title("Pauta de exportação conteinerizada — % das toneladas (top 10 grupos)")
    ax.set_ylabel("Participação")
    ax.legend(loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize=8)
    salvar(fig, "08_pauta_conteinerizada_export")

    # Indústria vs commodity heurístico
    pads = pct.columns.str.lower()
    is_commod = pads.str.contains("agric|grão|gran|carne|peixe|pesc|madeir|tabaco|alg|cafe|café|açúcar|acucar", regex=True)
    is_indust = pads.str.contains("máquin|maqui|equip|veíc|veic|metal|aço|ferro|químic|quimic|plást|plast|eletro|farm|têxt|text", regex=True)
    com = pct.loc[:, is_commod].sum(axis=1)
    ind = pct.loc[:, is_indust].sum(axis=1)
    delta_com = com.iloc[-1] - com.iloc[0]
    delta_ind = ind.iloc[-1] - ind.iloc[0]
    print(f"  Top grupo exportado (média do período): {pct.mean().idxmax()}")
    print(f"  Δ commodities (2010→{int(pct.index[-1])}): {delta_com:+.1%}")
    print(f"  Δ industria   (2010→{int(pct.index[-1])}): {delta_ind:+.1%}")
    if delta_com > 0.03 and delta_ind < 0:
        print("  → Sinal de comoditização: pauta dentro do contêiner está se commoditizando.")
    elif delta_ind > 0.03:
        print("  → Sinal de industrialização: produtos manufaturados ganharam share.")
    else:
        print("  → Pauta relativamente estável.")
    return pct


# ─── 09 — Vazio estrutural vs sazonal ─────────────────────────────────────────
def a09_vazio_sazonal():
    secao(9, "Vazio estrutural vs sazonal")
    db = conectar()
    df = db.sql(
        """
        SELECT date_trunc('month', a."Data Atracação")::DATE AS mes,
               c.Sentido,
               SUM(CASE WHEN c.ConteinerEstado='Cheio' THEN 1 ELSE 0 END) AS cheio,
               SUM(CASE WHEN c.ConteinerEstado='Vazio' THEN 1 ELSE 0 END) AS vazio
        FROM Carga c JOIN Atracacao a USING(IDAtracacao)
        WHERE c."Natureza da Carga"='Carga Conteinerizada'
          AND c.FlagLongoCurso = 1
          AND a."Data Atracação" >= '2015-01-01' AND a."Data Atracação" < '2026-01-01'
        GROUP BY 1,2 ORDER BY 1
        """
    ).df()
    emb = df[df.Sentido=="Embarcados"].copy()
    emb["pct_vazio"] = emb["vazio"] / (emb["cheio"] + emb["vazio"])
    emb["mes_num"] = emb["mes"].dt.month
    emb["ano"]     = emb["mes"].dt.year

    estrutural = emb.groupby("ano")["pct_vazio"].mean()
    sazonal    = emb.groupby("mes_num")["pct_vazio"].mean()

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    axes[0].plot(estrutural.index, estrutural.values, marker="o", color="#3a64a8")
    axes[0].set_title("Estrutural — % vazios embarcados por ano")
    axes[0].set_ylabel("% vazios em embarques")
    axes[1].plot(sazonal.index, sazonal.values, marker="o", color="#c1322f")
    axes[1].set_xticks(range(1, 13))
    axes[1].set_title("Sazonal — % vazios embarcados por mês (média)")
    axes[1].set_xlabel("Mês")
    salvar(fig, "09_vazio_estrutural_sazonal")

    amplitude_saz = sazonal.max() - sazonal.min()
    amplitude_est = estrutural.max() - estrutural.min()
    print(f"  Amplitude estrutural (ano-a-ano):  {amplitude_est:.1%}")
    print(f"  Amplitude sazonal    (mês-a-mês):  {amplitude_saz:.1%}")
    print(f"  Mês de pico de vazios: {int(sazonal.idxmax())}  ({sazonal.max():.1%})")
    print(f"  Mês de mínimo:         {int(sazonal.idxmin())}  ({sazonal.min():.1%})")
    if amplitude_saz < amplitude_est * 0.5:
        print("  → Predomínio estrutural: vazios são problema de fluxo bilateral, não calendário.")
    else:
        print("  → Componente sazonal relevante: oportunidade de planejar reposicionamento por safra.")
    return emb


def main():
    a06_desequilibrio_cheio_vazio()
    a07_proxy_cambio()
    a08_conteudo_conteineres()
    a09_vazio_sazonal()


if __name__ == "__main__":
    main()
