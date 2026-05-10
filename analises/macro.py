"""
Helpers para séries macroeconômicas do BCB SGS, com cache local em parquet.

Uso:
    from analises.macro import sgs, usdbrl_anual, pib_real_anual, pim_pf

    cambio_anual = usdbrl_anual()         # pd.Series indexada por ano
    pib_anual    = pib_real_anual()       # pd.Series indexada por ano (%)
    pim          = pim_pf()               # pd.Series mensal

Códigos SGS de interesse para esta base portuária:
    3697   — USD/BRL PTAX venda — média mensal
    7326   — PIB real — variação acumulada em 4 trimestres (%)
    24364  — IBC-Br dessazonalizado — proxy mensal de atividade
    28503  — PIM-PF Indústria Geral dessazonalizado
    433    — IPCA — variação mensal (%)
    432    — Selic meta (% a.a.)
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import pandas as pd

CACHE = Path(__file__).resolve().parent.parent / "parquet" / "cache"
CACHE.mkdir(parents=True, exist_ok=True)


def sgs(codigo: int,
        inicio: str = "01/01/2010",
        fim: str    = "31/12/2026",
        force: bool = False) -> pd.Series:
    """Baixa série do BCB SGS com cache. Datas no formato dd/mm/aaaa."""
    arq = CACHE / f"sgs_{codigo}.parquet"
    if arq.exists() and not force:
        return pd.read_parquet(arq).iloc[:, 0]
    url = (f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
           f"?formato=json&dataInicial={inicio}&dataFinal={fim}")
    raw = json.loads(urllib.request.urlopen(url, timeout=30).read())
    if not raw:
        raise ValueError(f"SGS {codigo}: resposta vazia.")
    s = (pd.DataFrame(raw)
            .assign(data=lambda d: pd.to_datetime(d["data"], format="%d/%m/%Y"),
                    valor=lambda d: d["valor"].astype(float))
            .set_index("data")["valor"]
            .sort_index()
            .rename(f"sgs_{codigo}"))
    s.to_frame().to_parquet(arq)
    return s


# ─── Séries derivadas, prontas para uso ───────────────────────────────────────
def usdbrl_mensal() -> pd.Series:
    """Câmbio USD/BRL — média mensal PTAX venda (SGS 3697)."""
    return sgs(3697).rename("usdbrl")


def usdbrl_anual() -> pd.Series:
    """USD/BRL anual = média simples das médias mensais."""
    s = usdbrl_mensal()
    return s.groupby(s.index.year).mean().rename("usdbrl_anual")


def pib_real_anual() -> pd.Series:
    """
    PIB real — variação anual (%).

    Usa SGS 7326 (acumulado em 4 trimestres). O valor de janeiro de cada ano
    representa o crescimento do ano-calendário anterior fechado, então
    deslocamos -1 ano para indexar pelo ano de referência.
    """
    s = sgs(7326)
    # mantém apenas a observação anual (jan ou último ponto do ano)
    anual = s.groupby(s.index.year).last()
    return anual.rename("pib_real_pct_aa")


def ibc_br() -> pd.Series:
    """IBC-Br dessazonalizado — proxy mensal do PIB (SGS 24364)."""
    return sgs(24364).rename("ibc_br")


def ipca_mensal() -> pd.Series:
    """IPCA — variação mensal (%) (SGS 433)."""
    return sgs(433).rename("ipca_mensal")


def selic_meta() -> pd.Series:
    """Selic meta diária (% a.a.) (SGS 432)."""
    return sgs(432).rename("selic_meta")


def pim_pf() -> pd.Series:
    """PIM-PF Indústria Geral dessazonalizada (SGS 28503)."""
    return sgs(28503).rename("pim_pf")


def atualizar_cache(codigos: list[int] | None = None) -> None:
    """Força re-download das séries listadas (ou todas conhecidas)."""
    todos = codigos or [3697, 7326, 24364, 28503, 433, 432]
    for c in todos:
        try:
            sgs(c, force=True)
            print(f"  ✓ SGS {c} atualizado")
        except Exception as e:
            print(f"  ✗ SGS {c}: {e}")


if __name__ == "__main__":
    print("Atualizando cache de séries BCB SGS...")
    atualizar_cache()
    print("\nResumo das séries em cache:")
    for arq in sorted(CACHE.glob("sgs_*.parquet")):
        s = pd.read_parquet(arq).iloc[:, 0]
        print(f"  {arq.stem:12s}  {len(s):5d} pontos  "
              f"{s.index.min().date()} → {s.index.max().date()}")
