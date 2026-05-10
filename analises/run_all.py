"""
Roda as 29 análises (todos os clusters), salvando figuras em figs/analises/.

Uso:
    python -m analises.run_all
    python -m analises.run_all c1 c3        # só clusters específicos
"""
from __future__ import annotations
import sys
import time
import traceback

CLUSTERS = {
    "c1": ("Eficiência operacional",   "analises.c1_eficiencia"),
    "c2": ("Contêineres",              "analises.c2_conteineres"),
    "c3": ("Cabotagem e hidrovias",    "analises.c3_cabotagem_hidrovias"),
    "c4": ("Geopolítica",              "analises.c4_geopolitica"),
    "c5": ("Infraestrutura",           "analises.c5_infraestrutura"),
    "c6": ("Agronegócio",              "analises.c6_agronegocio"),
    "c7": ("Análises inéditas",        "analises.c7_ineditas"),
}


def main(filtros: list[str] | None = None) -> None:
    selecao = list(CLUSTERS) if not filtros else [k for k in filtros if k in CLUSTERS]
    print(f"\n  Executando {len(selecao)} clusters: {', '.join(selecao)}")
    inicio = time.time()
    falhas = []

    for chave in selecao:
        nome, mod = CLUSTERS[chave]
        print(f"\n\n{'═'*78}\n  {chave.upper()} — {nome}\n{'═'*78}")
        t0 = time.time()
        try:
            modulo = __import__(mod, fromlist=["main"])
            modulo.main()
        except Exception as e:
            print(f"\n  ✗ FALHA em {chave}: {e}")
            traceback.print_exc()
            falhas.append((chave, str(e)))
        else:
            print(f"\n  ✓ {chave} concluído em {time.time()-t0:.1f}s")

    total = time.time() - inicio
    print(f"\n\n{'═'*78}")
    print(f"  TOTAL: {len(selecao)} clusters em {total:.0f}s ({total/60:.1f} min)")
    if falhas:
        print(f"  Falhas: {len(falhas)}")
        for c, e in falhas:
            print(f"    {c}: {e}")
    else:
        print("  Todas as análises rodaram com sucesso.")
    print(f"  Figuras: figs/analises/*.png")
    print(f"{'═'*78}\n")


if __name__ == "__main__":
    main(sys.argv[1:] or None)
