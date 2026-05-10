"""
Cluster 4 — Geopolítica

14. Concentração geográfica das exportações  — HHI dos destinos por NCM
15. Dependência de importação                — % vindo de país único (vulnerabilidade)
16. Impacto de eventos geopolíticos           — Rússia-Ucrânia 2022, COVID 2020
17. Blocos econômicos                          — Mercosul, UE, China, EUA
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from .utils import conectar, salvar, secao


# Mapeamento de país → bloco
BLOCOS = {
    "MERCOSUL": ["ARGENTINA", "URUGUAI", "PARAGUAI", "VENEZUELA", "BOLÍVIA", "BOLIVIA"],
    "UE": ["ALEMANHA", "FRANÇA", "FRANCA", "ITÁLIA", "ITALIA", "ESPANHA", "PORTUGAL",
           "PAÍSES BAIXOS", "PAISES BAIXOS", "HOLANDA", "BÉLGICA", "BELGICA",
           "POLÔNIA", "POLONIA", "DINAMARCA", "SUÉCIA", "SUECIA", "FINLÂNDIA", "FINLANDIA",
           "ÁUSTRIA", "AUSTRIA", "GRÉCIA", "GRECIA", "IRLANDA", "REPÚBLICA TCHECA",
           "REPUBLICA TCHECA", "HUNGRIA", "ROMÊNIA", "ROMENIA", "BULGÁRIA", "BULGARIA",
           "CROÁCIA", "CROACIA", "ESLOVÁQUIA", "ESLOVAQUIA", "ESLOVÊNIA", "ESLOVENIA",
           "ESTÔNIA", "ESTONIA", "LETÔNIA", "LETONIA", "LITUÂNIA", "LITUANIA",
           "LUXEMBURGO", "MALTA", "CHIPRE"],
    "CHINA": ["CHINA", "HONG KONG", "TAIWAN"],
    "EUA": ["ESTADOS UNIDOS"],
    "RUSSIA_UCR": ["RÚSSIA", "RUSSIA", "FEDERAÇÃO RUSSA", "FEDERACAO RUSSA",
                   "UCRÂNIA", "UCRANIA"],
    "ASIA_OUTROS": ["JAPÃO", "JAPAO", "COREIA DO SUL", "COREIA", "ÍNDIA", "INDIA",
                    "VIETNÃ", "VIETNA", "INDONÉSIA", "INDONESIA", "TAILÂNDIA",
                    "TAILANDIA", "MALÁSIA", "MALASIA", "FILIPINAS", "PAQUISTÃO",
                    "PAQUISTAO", "SINGAPURA", "ARÁBIA SAUDITA", "ARABIA SAUDITA",
                    "EMIRADOS ÁRABES UNIDOS", "EMIRADOS ARABES UNIDOS", "IRÃ", "IRA",
                    "IRAQUE", "ISRAEL", "TURQUIA"],
}


def _bloco(pais) -> str:
    if pais is None or (isinstance(pais, float) and np.isnan(pais)) or not str(pais).strip():
        return "OUTROS"
    p = str(pais).upper().strip()
    for bloco, paises in BLOCOS.items():
        if p in paises:
            return bloco
    return "OUTROS"


# ─── 14 — HHI dos destinos por NCM ────────────────────────────────────────────
def a14_hhi_destinos(top_ncms: int = 8):
    secao(14, "Concentração geográfica das exportações (HHI por NCM)")
    db = conectar()

    df = db.sql(
        """
        SELECT c.Ano,
               m."Mercadoria"           AS mercadoria,
               UPPER(d."País Destino") AS pais,
               SUM(c.VLPesoCargaBruta) AS ton
        FROM Carga c
        JOIN Mercadoria m         ON c.CDMercadoria = m.CDMercadoria
        JOIN InstalacaoDestino d  ON c.Destino      = d.Destino
        WHERE c.FlagLongoCurso = 1
          AND c.Sentido = 'Embarcados'
          AND c.Ano BETWEEN 2010 AND 2025
        GROUP BY 1,2,3
        """
    ).df()

    # HHI por mercadoria-ano (× 10000)
    df["share"] = (df.groupby(["Ano", "mercadoria"])["ton"]
                     .transform(lambda s: s / s.sum()))
    hhi = (df.assign(s2=df["share"]**2)
             .groupby(["Ano", "mercadoria"])["s2"].sum() * 10_000).reset_index(name="HHI")

    # Top mercadorias por volume
    top = (df.groupby("mercadoria")["ton"].sum()
              .sort_values(ascending=False).head(top_ncms).index.tolist())
    sub = hhi[hhi["mercadoria"].isin(top)].pivot(index="Ano", columns="mercadoria", values="HHI")

    fig, ax = plt.subplots(figsize=(12, 6))
    sub.plot(ax=ax, lw=1.8)
    ax.axhline(2500, color="red", lw=1, ls="--", alpha=0.5)
    ax.text(2010, 2550, "HHI > 2500 = altamente concentrado", color="red", fontsize=8)
    ax.set_ylabel("HHI dos destinos (×10⁴)")
    ax.set_title(f"Concentração geográfica das exportações — top {top_ncms} mercadorias")
    ax.legend(loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize=7)
    salvar(fig, "14_hhi_exportacoes")

    media_recente = hhi.query("Ano>=2022").groupby("mercadoria")["HHI"].mean()
    media_recente = media_recente.loc[media_recente.index.isin(top)].sort_values(ascending=False)
    print(f"  Mercadoria mais concentrada (2022-25): {media_recente.idxmax()[:50]}")
    print(f"    HHI médio = {media_recente.max():.0f}")
    print(f"  Mercadoria mais diversificada:        {media_recente.idxmin()[:50]}")
    print(f"    HHI médio = {media_recente.min():.0f}")
    print(f"  HHI = soma dos shares² × 10⁴; >2500 ≈ altamente concentrado.")
    return sub


# ─── 15 — Dependência de importação por mercadoria ────────────────────────────
def a15_dependencia_importacao(focos: tuple[str, ...] = ("FERTILIZANT", "ADUB", "COMBUST", "POTÁSS", "URÉIA")):
    secao(15, "Dependência de importação — % de país único")
    db = conectar()

    df = db.sql(
        f"""
        SELECT c.Ano,
               m."Mercadoria" AS mercadoria,
               UPPER(o."País Origem") AS pais_origem,
               SUM(c.VLPesoCargaBruta) AS ton
        FROM Carga c
        JOIN Mercadoria m         ON c.CDMercadoria = m.CDMercadoria
        JOIN InstalacaoOrigem o   ON c.Origem       = o.Origem
        WHERE c.FlagLongoCurso = 1
          AND c.Sentido = 'Desembarcados'
          AND c.Ano BETWEEN 2010 AND 2025
        GROUP BY 1,2,3
        """
    ).df()

    foco_re = "|".join(focos)
    df = df[df["mercadoria"].str.upper().str.contains(foco_re, na=False, regex=True)]
    if df.empty:
        print("  Nenhuma mercadoria encontrada com filtros — ajustar 'focos'.")
        return df

    # Normaliza grupo
    def grupo(s):
        s = s.upper()
        if "FERTILIZANT" in s or "ADUB" in s or "POTÁSS" in s or "URÉIA" in s or "URÉI" in s:
            return "Fertilizantes"
        if "COMBUST" in s or "ÓLEO" in s or "GASOL" in s or "DIESEL" in s:
            return "Combustíveis"
        return "Outro"
    df["grupo"] = df["mercadoria"].map(grupo)

    g = df.groupby(["Ano", "grupo", "pais_origem"])["ton"].sum().reset_index()
    g["share"] = g.groupby(["Ano", "grupo"])["ton"].transform(lambda s: s / s.sum())
    top1 = (g.sort_values("share", ascending=False)
              .groupby(["Ano", "grupo"]).head(1))

    fig, ax = plt.subplots()
    for grupo_n, sub in top1.groupby("grupo"):
        ax.plot(sub["Ano"], sub["share"]*100, marker="o", lw=1.8, label=grupo_n)
        for _, r in sub.iterrows():
            if r["Ano"] in (sub["Ano"].iloc[0], sub["Ano"].iloc[-1]):
                ax.annotate(r["pais_origem"][:3], (r["Ano"], r["share"]*100),
                            fontsize=7, ha="center", va="bottom")
    ax.set_ylabel("% de toneladas vindas do principal fornecedor")
    ax.set_title("Dependência de importação — share do maior fornecedor por ano")
    ax.axhline(50, color="grey", lw=0.5, ls="--")
    ax.legend(framealpha=0.9)
    salvar(fig, "15_dependencia_importacao")

    fert_2024 = top1.query("grupo=='Fertilizantes' & Ano==2024")
    if not fert_2024.empty:
        r = fert_2024.iloc[0]
        print(f"  Fertilizantes 2024 — maior fornecedor: {r.pais_origem[:30]} ({r.share:.0%})")
    comb_2024 = top1.query("grupo=='Combustíveis' & Ano==2024")
    if not comb_2024.empty:
        r = comb_2024.iloc[0]
        print(f"  Combustíveis 2024 — maior fornecedor:  {r.pais_origem[:30]} ({r.share:.0%})")
    print("  Share > 50% indica vulnerabilidade a choques no fornecedor único.")
    return top1


# ─── 16 — Eventos geopolíticos ────────────────────────────────────────────────
def a16_eventos_geopoliticos():
    secao(16, "Eventos geopolíticos — Rússia-Ucrânia 2022, COVID 2020")
    db = conectar()
    df = db.sql(
        """
        SELECT date_trunc('month', a."Data Atracação")::DATE AS mes,
               c.Sentido,
               CASE
                 WHEN UPPER(o."País Origem")  IN ('RÚSSIA','RUSSIA','UCRÂNIA','UCRANIA',
                       'FEDERAÇÃO RUSSA','FEDERACAO RUSSA') THEN 'RUS+UCR'
                 WHEN UPPER(d."País Destino") IN ('RÚSSIA','RUSSIA','UCRÂNIA','UCRANIA',
                       'FEDERAÇÃO RUSSA','FEDERACAO RUSSA') THEN 'RUS+UCR'
                 WHEN UPPER(o."País Origem") = 'CHINA' OR UPPER(d."País Destino")='CHINA' THEN 'CHINA'
                 WHEN UPPER(o."País Origem") = 'ESTADOS UNIDOS' OR UPPER(d."País Destino")='ESTADOS UNIDOS' THEN 'EUA'
                 ELSE 'OUTROS'
               END AS bloco,
               SUM(c.VLPesoCargaBruta) AS ton
        FROM Carga c
        JOIN Atracacao a USING(IDAtracacao)
        LEFT JOIN InstalacaoOrigem  o ON c.Origem  = o.Origem
        LEFT JOIN InstalacaoDestino d ON c.Destino = d.Destino
        WHERE c.FlagLongoCurso = 1
          AND a."Data Atracação" >= '2018-01-01' AND a."Data Atracação" < '2026-01-01'
        GROUP BY 1,2,3
        """
    ).df()

    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    for ax, sent in zip(axes, ("Embarcados", "Desembarcados")):
        sub = (df[df.Sentido==sent]
                 .pivot_table(index="mes", columns="bloco", values="ton",
                              aggfunc="sum", fill_value=0))
        sub_roll = sub.rolling(3, center=True).mean()
        sub_roll.plot(ax=ax, lw=1.8, cmap="tab10")
        ax.axvspan(pd.Timestamp("2020-03-01"), pd.Timestamp("2020-12-01"),
                   alpha=0.10, color="grey", label="COVID")
        ax.axvline(pd.Timestamp("2022-02-24"), color="red", lw=1, ls="--", label="Rússia × Ucrânia")
        ax.set_title(f"{sent} — toneladas mensais (média móvel 3m)")
        ax.legend(framealpha=0.9, fontsize=7, ncols=3)
    salvar(fig, "16_eventos_geopoliticos")

    rus_anual = (df[df.bloco=="RUS+UCR"]
                   .assign(ano=df["mes"].dt.year)
                   .groupby(["ano", "Sentido"])["ton"].sum()
                   .unstack("Sentido", fill_value=0))
    rus_anual["TOTAL"] = rus_anual.sum(axis=1)
    print("  Volume com Rússia+Ucrânia (Mt/ano):")
    print(rus_anual.div(1e6).round(2).to_string())
    return df


# ─── 17 — Blocos econômicos ───────────────────────────────────────────────────
def a17_blocos_economicos():
    secao(17, "Blocos econômicos — Mercosul, UE, China, EUA")
    db = conectar()
    df = db.sql(
        """
        SELECT c.Ano,
               c.Sentido,
               UPPER(CASE WHEN c.Sentido='Embarcados'
                          THEN d."País Destino"
                          ELSE o."País Origem" END) AS pais,
               SUM(c.VLPesoCargaBruta) AS ton
        FROM Carga c
        LEFT JOIN InstalacaoOrigem  o ON c.Origem  = o.Origem
        LEFT JOIN InstalacaoDestino d ON c.Destino = d.Destino
        WHERE c.FlagLongoCurso = 1
          AND c.Ano BETWEEN 2010 AND 2025
        GROUP BY 1,2,3
        """
    ).df()
    df["bloco"] = df["pais"].map(_bloco)

    g = (df.groupby(["Ano", "Sentido", "bloco"])["ton"].sum()
            .unstack("bloco", fill_value=0))
    g_pct = g.div(g.sum(axis=1), axis=0)

    fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharey=True)
    for ax, sent in zip(axes, ("Embarcados", "Desembarcados")):
        sub = g_pct.xs(sent, level="Sentido")
        sub.plot.area(ax=ax, cmap="tab10", lw=0)
        ax.set_title(f"{sent} — share dos blocos")
        ax.set_ylabel("Participação (%)")
        ax.set_ylim(0, 1)
        ax.legend(loc="upper right", fontsize=7, ncols=2)
    salvar(fig, "17_blocos_economicos")

    emb = g_pct.xs("Embarcados", level="Sentido")
    print(f"  China share exportações: {emb.CHINA.iloc[0]:.0%} (2010) → {emb.CHINA.iloc[-1]:.0%} ({int(emb.index[-1])})")
    print(f"  UE   share exportações: {emb.UE.iloc[0]:.0%} → {emb.UE.iloc[-1]:.0%}")
    print(f"  EUA  share exportações: {emb.EUA.iloc[0]:.0%} → {emb.EUA.iloc[-1]:.0%}")
    if emb.CHINA.iloc[-1] > emb.CHINA.iloc[0] + 0.05:
        print("  → Forte trade diversion: China captura share de outras regiões.")
    return g_pct


def main():
    a14_hhi_destinos()
    a15_dependencia_importacao()
    a16_eventos_geopoliticos()
    a17_blocos_economicos()


if __name__ == "__main__":
    main()
