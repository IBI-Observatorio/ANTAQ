"""Helpers compartilhados pelas análises."""

from pathlib import Path
import sys
import matplotlib
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
FIGS = ROOT / "figs" / "analises"
FIGS.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT))

import antaq  # noqa: E402

matplotlib.rcParams.update({
    "figure.figsize": (10, 5.5),
    "figure.dpi": 110,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linestyle": "--",
    "font.size": 10,
})


def conectar():
    """Retorna conexão DuckDB com views básicas e analíticas registradas."""
    db = antaq.conectar()
    antaq.registrar_views(db)
    return db


def salvar(fig, nome: str) -> Path:
    """Salva figura em figs/analises/<nome>.png e fecha."""
    path = FIGS / f"{nome}.png"
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def secao(num: int, titulo: str) -> None:
    print()
    print("─" * 78)
    print(f"  Análise #{num:02d} — {titulo}")
    print("─" * 78)


def fmt(n: float, casas: int = 1) -> str:
    """Formata número grande: 1234567 → '1,2 M'."""
    if n is None:
        return "—"
    a = abs(n)
    if a >= 1e9:
        return f"{n/1e9:.{casas}f} G"
    if a >= 1e6:
        return f"{n/1e6:.{casas}f} M"
    if a >= 1e3:
        return f"{n/1e3:.{casas}f} k"
    return f"{n:.{casas}f}"
