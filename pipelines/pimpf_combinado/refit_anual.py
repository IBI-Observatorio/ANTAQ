"""
Refit anual do DFM-1f.

Re-estima o Dynamic Factor Model com janela expansiva completa
(jan/2014 até dez do ano anterior) usando exatamente a mesma
especificação validada no spike PortGDP v2:

    DynamicFactor(k_factors=1, factor_order=2,
                   error_order=0, error_var=False)

Salva o resultado serializado em models/dfm_AAAA.pkl, atualiza o
ponteiro models/dfm_atual.pkl e loga métricas em models/refit_log.md.

Frequência: anual, dia 5 de janeiro (cron 0 6 5 1 *).
NÃO sobrescreve modelos anteriores — auditabilidade.

Uso:
    python -m pipelines.pimpf_combinado.refit_anual
    python -m pipelines.pimpf_combinado.refit_anual --ano 2027
    python -m pipelines.pimpf_combinado.refit_anual --force  # reajusta o atual
"""
from __future__ import annotations

import argparse
import pickle
import sys
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from analises.validacao.portgdp_v2_walkforward import _ajustar_dfm  # noqa: E402

MODELS = ROOT / "models"
LOG    = MODELS / "refit_log.md"
SERIES = ROOT / "validacao" / "portgdp_v2" / "series_tratadas.parquet"

warnings.filterwarnings("ignore")


def _carregar_painel_var12m_padronizado(data_corte: pd.Timestamp) -> pd.DataFrame:
    """Mesmo painel da validação v2, restrito a [2014-01, data_corte]."""
    df = pd.read_parquet(SERIES).set_index("mes")
    df.index = pd.to_datetime(df.index)
    cols_v = [c for c in df.columns if c.startswith("var12m__")]
    var = df[cols_v].dropna(how="all").copy()
    var.columns = [c.replace("var12m__", "") for c in var.columns]
    var = var.loc[:data_corte]
    z = (var - var.mean()) / var.std(ddof=0)
    return z.dropna()


def refit(ano: int, force: bool = False) -> Path:
    arq = MODELS / f"dfm_{ano}.pkl"
    if arq.exists() and not force:
        print(f"  ja_existe: {arq.relative_to(ROOT)} (use --force para refit)")
        return arq

    MODELS.mkdir(parents=True, exist_ok=True)
    data_corte = pd.Timestamp(f"{ano - 1}-12-01")
    print(f"  Refit DFM-1f, janela 2014-01 até {data_corte.date()}…")

    Y = _carregar_painel_var12m_padronizado(data_corte)
    if len(Y) < 60:
        raise RuntimeError(f"painel insuficiente: {len(Y)} meses < 60")
    print(f"  Painel: {Y.shape[0]} meses × {Y.shape[1]} séries")

    res = _ajustar_dfm(Y.values, k_factors=1, factor_order=2)
    if not res.mle_retvals.get("converged", False):
        print(f"  ⚠ NÃO convergiu — modelo descartado, ano={ano}")
        return None

    # Calcula métricas in-sample para o log
    fitted = res.fittedvalues
    ss_res = float(np.nansum((Y.values - fitted) ** 2))
    ss_tot = float(np.nansum(Y.values ** 2))
    r2 = 1 - ss_res / ss_tot
    mae_in = float(np.nanmean(np.abs(Y.values - fitted)))

    payload = {
        "modelo_serializado": res,           # statsmodels Result
        "data_corte":         data_corte.isoformat(),
        "n_meses":            int(Y.shape[0]),
        "n_series":           int(Y.shape[1]),
        "colunas":            list(Y.columns),
        "media":              Y.mean(axis=0).to_dict(),
        "dp":                 Y.std(ddof=0, axis=0).to_dict(),
        "llf":                float(res.llf),
        "aic":                float(res.aic),
        "bic":                float(res.bic),
        "r2_painel":          float(r2),
        "mae_in_sample":      mae_in,
        "ano_refit":          ano,
        "data_refit_utc":     datetime.utcnow().isoformat(),
    }
    with open(arq, "wb") as f:
        pickle.dump(payload, f)
    print(f"  ✓ {arq.relative_to(ROOT)}")
    print(f"    LL = {res.llf:.1f}  AIC = {res.aic:.1f}  BIC = {res.bic:.1f}  "
          f"R² = {r2:.3f}  MAE_in = {mae_in:.4f}")

    # Atualiza ponteiro
    atual = MODELS / "dfm_atual.pkl"
    if atual.exists():
        atual.unlink()
    # Em Windows symlink exige privilégio; copiamos o arquivo.
    import shutil
    shutil.copyfile(arq, atual)
    print(f"  ✓ {atual.relative_to(ROOT)} (ponteiro atualizado)")

    # Append no log
    LOG.parent.mkdir(parents=True, exist_ok=True)
    novo = not LOG.exists()
    with open(LOG, "a", encoding="utf-8") as f:
        if novo:
            f.write("# Refit log — DFM-1f\n\n"
                     "| ano | data_corte | n_meses | n_series | LL | AIC | BIC | R² | MAE_in |\n"
                     "|---|---|---|---|---|---|---|---|---|\n")
        f.write(f"| {ano} | {data_corte.date()} | "
                 f"{payload['n_meses']} | {payload['n_series']} | "
                 f"{res.llf:.1f} | {res.aic:.1f} | {res.bic:.1f} | "
                 f"{r2:.3f} | {mae_in:.4f} |\n")
    print(f"  ✓ {LOG.relative_to(ROOT)}")
    return arq


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ano", type=int, default=None,
                        help="Ano do refit. Default: ano atual.")
    parser.add_argument("--force", action="store_true",
                        help="Refaz mesmo se modelo do ano já existe.")
    args = parser.parse_args()

    ano = args.ano or datetime.utcnow().year
    print(f"\n  ── refit_anual — ano {ano} ──")
    refit(ano, force=args.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
