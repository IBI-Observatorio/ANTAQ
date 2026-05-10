"""
Confronta previsões antigas em historico.csv com realizados novos do
PIM-PF (BCB SGS 28503) e preenche realizado, erro, dentro_intervalo.

Também calcula:
  - MAE rolling 12 meses considerando apenas previsões em produção
  - Cobertura empírica acumulada das previsões em produção

Salva métricas separadas em data/previsoes/track_record_producao.csv.

Idempotente — rodar duas vezes não muda nada se não houver realizado novo.

Uso:
    python -m pipelines.pimpf_combinado.atualiza_realizados
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from analises.macro import sgs                       # noqa: E402

HIST = ROOT / "data" / "previsoes" / "historico.csv"
TRACK = ROOT / "data" / "previsoes" / "track_record_producao.csv"


def main() -> int:
    print("\n  ── atualiza_realizados ──")
    if not HIST.exists():
        print(f"  ✗ falta {HIST.relative_to(ROOT)}")
        return 1

    df = pd.read_csv(HIST, parse_dates=["mes_alvo", "data_emissao"])
    n_pre = df["realizado"].notna().sum()

    pim = sgs(28503)
    pim_idx = pim / pim.loc["2014-01":"2014-12"].mean() * 100
    pim_var = pim_idx.pct_change(12)

    n_atualizadas = 0
    for i, r in df.iterrows():
        if pd.notna(r["realizado"]) and r["realizado"] != "":
            continue
        alvo = r["mes_alvo"]
        if alvo not in pim_var.index or pd.isna(pim_var.loc[alvo]):
            continue
        y_obs = float(pim_var.loc[alvo])
        y_hat = float(r["previsao_pontual"])
        inf = float(r["intervalo_inferior_80"])
        sup = float(r["intervalo_superior_80"])
        df.at[i, "realizado"] = round(y_obs, 6)
        df.at[i, "erro"] = round(abs(y_obs - y_hat), 6)
        df.at[i, "dentro_intervalo"] = bool(inf <= y_obs <= sup)
        n_atualizadas += 1

    df.to_csv(HIST, index=False, float_format="%.6f")
    print(f"  {n_atualizadas} previsões atualizadas com realizado.")
    print(f"  Total no histórico: {len(df)} linhas, "
          f"{df['realizado'].notna().sum()} com realizado.")

    # Métricas em produção (separadas)
    prod = df[(df["tipo"] == "producao") &
                df["realizado"].notna() & (df["realizado"] != "")].copy()
    prod = prod[pd.to_numeric(prod["realizado"], errors="coerce").notna()]
    if len(prod) > 0:
        prod["realizado"] = pd.to_numeric(prod["realizado"])
        prod["erro"] = pd.to_numeric(prod["erro"])
        prod = prod.sort_values("mes_alvo")

        mae_total_pp = float(prod["erro"].mean()) * 100
        mae_12m_pp   = float(prod["erro"].tail(12).mean()) * 100
        cobertura    = float(prod["dentro_intervalo"].astype(bool).mean())
        n_total      = len(prod)
        n_12m        = min(12, n_total)

        track = pd.DataFrame([{
            "data_calculo":    datetime.utcnow().strftime("%Y-%m-%d"),
            "n_previsoes_producao":      n_total,
            "n_previsoes_12m":           n_12m,
            "mae_producao_total_pp":     round(mae_total_pp, 4),
            "mae_producao_rolling12m_pp": round(mae_12m_pp, 4),
            "cobertura_empirica":        round(cobertura, 4),
            "primeira_previsao_alvo":    prod["mes_alvo"].iloc[0].strftime("%Y-%m"),
            "ultima_previsao_alvo":      prod["mes_alvo"].iloc[-1].strftime("%Y-%m"),
        }])
        TRACK.parent.mkdir(parents=True, exist_ok=True)
        novo = not TRACK.exists()
        track.to_csv(TRACK, mode="a", header=novo, index=False)
        print(f"\n  Métricas em produção (n={n_total}):")
        print(f"    MAE total: {mae_total_pp:.2f} pp")
        print(f"    MAE rolling 12m: {mae_12m_pp:.2f} pp")
        print(f"    Cobertura empírica: {cobertura:.1%}")
        print(f"  ✓ {TRACK.relative_to(ROOT)}")
    else:
        print("\n  (Sem previsões em produção com realizado disponível ainda.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
