"""
Dia 4 + Dia 5 — Bateria comparativa e aplicação mecânica da regra.

Lê:
    validacao/portgdp_v2/walkforward_dfm_previsoes.csv  (DFM-1f, DFM-2f)
    validacao/portgdp/walkforward_ardl_previsoes.csv     (AR(1), ARDL — v1)
    + walk-forward original com baselines (RW, sazonal naive)

Rodar:
    1. Combinar todos os modelos no mesmo CSV long.
    2. Métricas (resumir).
    3. DM-HLN: DFM-1f vs AR(1), DFM-2f vs AR(1), DFM (melhor) vs ARDL.
    4. Encompassing test (convenção corrigida): (AR(1), DFM) buscando
       rejeitar H0 — sinal de que DFM agrega.
    5. Granger-Ramanathan restrito: pesos DFM/AR(1).
    6. Aplicar regra A–E pré-registrada.

Outputs:
    validacao/portgdp_v2/dm_completo.csv
    validacao/portgdp_v2/encompassing.csv
    validacao/portgdp_v2/granger_ramanathan.csv
    validacao/portgdp_v2/sumario_executivo.md
"""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from analises.validacao.metricas import (resumir, dm_pareado, dm_test_hln,
                                           encompassing_test_hln,
                                           combinacao_otima_sum1)

OUT = ROOT / "validacao" / "portgdp_v2"
OUT_V1 = ROOT / "validacao" / "portgdp"


# ─── Coleta dos modelos comparáveis ───────────────────────────────────────────
def coletar_previsoes() -> pd.DataFrame:
    """
    Junta DFM-1f, DFM-2f (v2) com AR(1), ARDL, RW, sazonal_naive (v1).
    Garante coluna 'q50' presente em todos os modelos.
    """
    dfs = []
    arq_dfm = OUT / "walkforward_dfm_previsoes.csv"
    if not arq_dfm.exists():
        raise FileNotFoundError(f"Falta {arq_dfm}. Rode portgdp_v2_walkforward primeiro.")
    dfm = pd.read_csv(arq_dfm, parse_dates=["origem", "alvo"])
    dfs.append(dfm)

    # v1: AR(1), ARDL, ens_mediana, ens_media (do CSV ARDL)
    arq_v1_ardl = OUT_V1 / "walkforward_ardl_previsoes.csv"
    if arq_v1_ardl.exists():
        ardl = pd.read_csv(arq_v1_ardl, parse_dates=["origem", "alvo"])
        # Pega só ar1 e ardl (não ens_*)
        ardl = ardl[ardl["modelo"].isin(["ar1", "ardl"])]
        dfs.append(ardl)

    # v1 originais: portgdp_ols, rw, sazonal_naive
    arq_v1_orig = OUT_V1 / "walkforward_previsoes.csv"
    if arq_v1_orig.exists():
        orig = pd.read_csv(arq_v1_orig, parse_dates=["origem", "alvo"])
        orig = orig[orig["modelo"].isin(["rw", "sazonal_naive"])]
        dfs.append(orig)

    df = pd.concat(dfs, ignore_index=True)
    if "q50" not in df.columns:
        df["q50"] = df.get("media")
    df["q50"] = df["q50"].fillna(df.get("media"))

    # Alinhamento por (alvo, h, modelo): mantém apenas alvos comuns
    return df


# ─── Granger-Ramanathan restrito ──────────────────────────────────────────────
def gr_restrito_dfm_vs_ar1(df: pd.DataFrame) -> pd.DataFrame:
    """Combinação ótima DFM vs AR(1) por horizonte, com soma=1."""
    rows = []
    for h in [1, 2]:
        sub = df[df["h"] == h]
        ar1 = sub[sub["modelo"] == "ar1"].set_index("alvo")
        for nome_dfm in ["dfm_1f", "dfm_2f"]:
            dfm_h = sub[sub["modelo"] == nome_dfm].set_index("alvo")
            comum = ar1.index.intersection(dfm_h.index)
            if len(comum) < 5:
                continue
            res = combinacao_otima_sum1(
                y_true=ar1.loc[comum, "y_true"].values,
                forecast_1=dfm_h.loc[comum, "q50"].values,
                forecast_2=ar1.loc[comum, "q50"].values,
                h=h,
            )
            res.update({"h": h, "f1": nome_dfm, "f2": "ar1"})
            rows.append(res)
    return pd.DataFrame(rows)


def encompassing_dfm_vs_ar1(df: pd.DataFrame) -> pd.DataFrame:
    """Encompassing test, ambas direções: DFM vs AR(1)."""
    rows = []
    for h in [1, 2]:
        sub = df[df["h"] == h]
        ar1 = sub[sub["modelo"] == "ar1"].set_index("alvo")
        for nome_dfm in ["dfm_1f", "dfm_2f"]:
            dfm_h = sub[sub["modelo"] == nome_dfm].set_index("alvo")
            comum = ar1.index.intersection(dfm_h.index)
            if len(comum) < 5:
                continue
            y = ar1.loc[comum, "y_true"].values
            f_dfm = dfm_h.loc[comum, "q50"].values
            f_ar1 = ar1.loc[comum, "q50"].values

            # H0_a: DFM encompasses AR(1)?
            t1 = encompassing_test_hln(y, forecast_encompasser=f_dfm,
                                            forecast_encompassed=f_ar1, h=h)
            t1.update({"h": h, "encompasser": nome_dfm, "encompassed": "ar1"})
            rows.append(t1)
            # H0_b: AR(1) encompasses DFM?  (relevante para regra)
            t2 = encompassing_test_hln(y, forecast_encompasser=f_ar1,
                                            forecast_encompassed=f_dfm, h=h)
            t2.update({"h": h, "encompasser": "ar1", "encompassed": nome_dfm})
            rows.append(t2)
    return pd.DataFrame(rows)


# ─── Regra de decisão pré-registrada ──────────────────────────────────────────
def aplicar_regra(df_pred: pd.DataFrame,
                  dm: pd.DataFrame,
                  enc: pd.DataFrame,
                  gr: pd.DataFrame,
                  alfa: float = 0.05) -> dict:
    """Aplica linha A–E mecanicamente conforme REGRA_DECISAO.md."""
    def _bate(modelo_alvo, baseline, h):
        sub = dm[(dm["modelo_alvo"] == modelo_alvo) &
                  (dm["baseline"] == baseline) &
                  (dm["h"] == h)]
        if sub.empty:
            return False
        r = sub.iloc[0]
        if not np.isfinite(r["dm_stat"]) or not np.isfinite(r["p_value"]):
            return False
        return (r["dm_stat"] < 0) and (r["p_value"] < alfa)

    # Identificar a melhor variante DFM por h (menor MAE):
    resumo = resumir(df_pred)
    dfm_melhor_por_h = {}
    for h in [1, 2]:
        sub = resumo[(resumo["h"] == h) & (resumo["modelo"].str.startswith("dfm"))]
        if sub.empty:
            continue
        dfm_melhor_por_h[h] = sub.sort_values("mae_pp").iloc[0]["modelo"]
    if not dfm_melhor_por_h:
        return {"linha": "E", "comunicacao": "DFM falhou em todas origens.",
                "detalhes": {"erro": "no_dfm_data"}}

    # Condições A/B
    bate_h1 = any(_bate(m, "ar1", 1) for m in ["dfm_1f", "dfm_2f"])
    bate_h2 = any(_bate(m, "ar1", 2) for m in ["dfm_1f", "dfm_2f"])

    if bate_h1 and bate_h2:
        return {"linha": "A",
                "comunicacao": ("Indicador antecedente do PIM-PF via fatores "
                                 "de comércio internacional — claim preditivo "
                                 "completo. DFM bate AR(1) em h=1 e h=2 com "
                                 "p<0,05."),
                "detalhes": {"bate_h1": True, "bate_h2": True}}

    if bate_h2 and not bate_h1:
        return {"linha": "B",
                "comunicacao": ("Indicador antecedente em horizonte bimestral. "
                                 "Modelo bate AR(1) em h=2 mas não em h=1."),
                "detalhes": {"bate_h1": False, "bate_h2": True}}

    # Condição C: GR atribui peso ≥ 15% ao DFM com p<0,10 e combinação
    # vence AR(1) por DM (teste explícito, não só MAE direto).
    cond_c = False
    detalhes_c = {}
    for h in [1, 2]:
        for nome_dfm in ["dfm_1f", "dfm_2f"]:
            sub_gr = gr[(gr["h"] == h) & (gr["f1"] == nome_dfm)]
            if sub_gr.empty:
                continue
            r = sub_gr.iloc[0]
            peso_significativo = (r["w_1"] >= 0.15) and (r["p_value"] < 0.10)
            if not peso_significativo:
                continue

            # Constrói série de combinação OOS com peso GR (full-sample como
            # aproximação OOS — padrão da literatura de combinação).
            # Comparação via DM-HLN.
            dfm_h = df_pred[(df_pred["h"] == h) &
                              (df_pred["modelo"] == nome_dfm)].set_index("alvo")
            ar1_h = df_pred[(df_pred["h"] == h) &
                              (df_pred["modelo"] == "ar1")].set_index("alvo")
            comum = dfm_h.index.intersection(ar1_h.index)
            if len(comum) < 5:
                continue
            y_v = ar1_h.loc[comum, "y_true"].values
            comb_v = (r["w_1"] * dfm_h.loc[comum, "q50"].values
                       + r["w_2"] * ar1_h.loc[comum, "q50"].values)
            ar1_v = ar1_h.loc[comum, "q50"].values
            err_comb = y_v - comb_v
            err_ar1  = y_v - ar1_v
            dm_stat, dm_p, dm_n = dm_test_hln(err_comb, err_ar1, h=h)
            comb_vence_ar1_dm = (dm_stat < 0) and (dm_p < alfa)

            if comb_vence_ar1_dm:
                cond_c = True
                detalhes_c[f"h{h}_{nome_dfm}"] = {
                    "w_dfm": r["w_1"], "p_value_w": r["p_value"],
                    "mae_combinado": r["mae_combinado"],
                    "mae_ar1": r["mae_f2"],
                    "dm_comb_vs_ar1": dm_stat,
                    "p_dm_comb_vs_ar1": dm_p,
                }

    if cond_c:
        return {"linha": "C",
                "comunicacao": ("Componente do modelo combinado IBI. DFM "
                                 "individualmente não vence AR(1), mas a "
                                 "combinação ótima (Granger-Ramanathan) "
                                 "atribui peso significativo ao DFM e tem "
                                 "MAE menor que AR(1) puro."),
                "detalhes": detalhes_c}

    # Condição D: encompassing rejeita "AR(1) encompasses DFM"
    enc_rejeita_ar1_enc_dfm = enc[
        (enc["encompasser"] == "ar1") &
        (enc["encompassed"].str.startswith("dfm")) &
        (enc["rejeita_H0"] == True)
    ]
    if len(enc_rejeita_ar1_enc_dfm) > 0:
        return {"linha": "D",
                "comunicacao": ("Comovimento estrutural com componente "
                                 "preditivo marginal. Encompassing rejeita "
                                 "que AR(1) encompasses DFM (ARDL agrega "
                                 "sinal além da autocorrelação), ainda que "
                                 "DM e GR não favoreçam."),
                "detalhes": enc_rejeita_ar1_enc_dfm.to_dict("records")}

    # Default: Linha E
    return {"linha": "E",
            "comunicacao": ("Linha E definitiva. PortGDP v1 sobe descritivo; "
                             "DFM v2 fica documentado como tentativa não-bem-"
                             "sucedida. Nenhum critério A–D satisfeito."),
            "detalhes": {"bate_h1": bate_h1, "bate_h2": bate_h2,
                         "cond_c": cond_c}}


# ─── Helpers de saída ─────────────────────────────────────────────────────────
def _md_table(df: pd.DataFrame, casas: int = 4) -> str:
    cols = list(df.columns)
    head = "| " + " | ".join(cols) + " |"
    sep  = "|" + "|".join("---" for _ in cols) + "|"
    rows = []
    for _, r in df.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            if isinstance(v, float):
                cells.append(f"{v:.{casas}f}")
            else:
                cells.append(str(v))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([head, sep, *rows])


# ─── Main ─────────────────────────────────────────────────────────────────────
def main() -> int:
    print("\n  ── Dia 4+5 — Bateria comparativa e decisão ──")
    print("\n  [1] Coletando previsões (DFM v2 + AR(1) + ARDL + baselines v1)…")
    df_pred = coletar_previsoes()
    print(f"    {len(df_pred):,} previsões totais. "
          f"Modelos: {sorted(df_pred['modelo'].unique())}")

    # ─── Métricas ───────────────────────────────────────────────────────────
    print("\n  [2] Métricas por (modelo × h)…")
    resumo = resumir(df_pred)
    print(resumo.to_string(index=False))

    # ─── DM-HLN ─────────────────────────────────────────────────────────────
    print("\n  [3] DM-HLN: DFM vs AR(1), DFM vs ARDL…")
    dm_dfm1f = dm_pareado(df_pred, modelo_alvo="dfm_1f", baselines=["ar1", "ardl"])
    dm_dfm2f = dm_pareado(df_pred, modelo_alvo="dfm_2f", baselines=["ar1", "ardl"])
    dm = pd.concat([dm_dfm1f, dm_dfm2f], ignore_index=True)
    dm.to_csv(OUT / "dm_completo.csv", index=False, float_format="%.6f")
    print(dm.to_string(index=False))

    # ─── Encompassing ───────────────────────────────────────────────────────
    print("\n  [4] Encompassing test (HLN 1998) DFM ↔ AR(1)…")
    enc = encompassing_dfm_vs_ar1(df_pred)
    cols_ordem = ["h", "encompasser", "encompassed", "lambda", "se_hac",
                   "t_stat", "p_value", "n", "rejeita_H0"]
    enc = enc[cols_ordem]
    enc.to_csv(OUT / "encompassing.csv", index=False, float_format="%.6f")
    print(enc[["h", "encompasser", "encompassed", "lambda",
                "p_value", "rejeita_H0"]].to_string(index=False))

    # ─── Granger-Ramanathan ─────────────────────────────────────────────────
    print("\n  [5] Granger-Ramanathan restrito (soma=1, sem intercepto, HAC)…")
    gr = gr_restrito_dfm_vs_ar1(df_pred)
    gr.to_csv(OUT / "granger_ramanathan.csv", index=False, float_format="%.6f")
    print(gr[["h", "f1", "f2", "w_1", "w_2", "p_value",
               "mae_combinado", "mae_f1", "mae_f2", "convexo"]]
            .to_string(index=False))

    # ─── Decisão ────────────────────────────────────────────────────────────
    print("\n  [6] Aplicando regra de decisão pré-registrada…")
    decisao = aplicar_regra(df_pred, dm, enc, gr)

    # ─── Sumário executivo ──────────────────────────────────────────────────
    md = []
    md.append("# Sumário executivo — Spike DFM PortGDP v2")
    md.append("")
    md.append(f"## → **Linha {decisao['linha']}**")
    md.append("")
    md.append(f"> {decisao['comunicacao']}")
    md.append("")
    md.append("## Detalhes")
    md.append("")
    md.append("```json")
    import json
    md.append(json.dumps(decisao.get("detalhes", {}), ensure_ascii=False,
                          indent=2, default=str))
    md.append("```")
    md.append("")
    md.append("## Métricas walk-forward (todos os modelos)")
    md.append("")
    md.append(_md_table(resumo, casas=3))
    md.append("")
    md.append("## DM-HLN — DFM vs AR(1), DFM vs ARDL")
    md.append("")
    md.append("Convenção: `dm_stat < 0` indica que `modelo_alvo` tem erro "
               "**menor** que `baseline`.")
    md.append("")
    md.append(_md_table(dm, casas=4))
    md.append("")
    md.append("## Encompassing test (HLN 1998)")
    md.append("")
    md.append("H0 testada: `encompasser` ENCOMPASSES `encompassed`. "
               "Rejeita H0 ⟺ `encompassed` agrega informação útil.")
    md.append("")
    md.append(_md_table(enc, casas=4))
    md.append("")
    md.append("## Granger-Ramanathan restrito (soma=1)")
    md.append("")
    md.append(_md_table(gr, casas=4))
    md.append("")
    (OUT / "sumario_executivo.md").write_text("\n".join(md), encoding="utf-8")
    print(f"\n  ✓ {(OUT / 'sumario_executivo.md').relative_to(ROOT)}")
    print(f"\n  ── DECISÃO: Linha {decisao['linha']} ──")
    print(f"  {decisao['comunicacao']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
