"""
Alertas automáticos de degradação do modelo em produção.

Gatilhos pré-registrados:
  G1: últimas 3 previsões em produção tiveram erro absoluto > 6 pp
      (= 2× MAE histórico de 3 pp validado).
      → label: degradacao-modelo
  G2: cobertura empírica acumulada em produção fora de [70%, 95%]
      depois de pelo menos 6 previsões em produção com realizado.
      → label: cobertura-fora-da-faixa

Quando ativado em ambiente CI (variável GITHUB_TOKEN presente),
abre uma issue via API REST do GitHub. Caso contrário, apenas imprime
o alerta no stdout (uso local / teste).

Uso:
    python -m pipelines.pimpf_combinado.verifica_degradacao
    GH_REPO=owner/repo GITHUB_TOKEN=... python -m pipelines.pimpf_combinado.verifica_degradacao
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
HIST = ROOT / "data" / "previsoes" / "historico.csv"

LIMITE_ERRO_PP   = 6.0  # 2× MAE histórico
N_ULTIMAS        = 3
COBERTURA_MIN    = 0.70
COBERTURA_MAX    = 0.95
N_MIN_COBERTURA  = 6


def _abrir_issue(titulo: str, corpo: str, labels: list[str]) -> bool:
    repo  = os.environ.get("GH_REPO")
    token = os.environ.get("GITHUB_TOKEN")
    if not (repo and token):
        print(f"\n  ⚠ ALERTA (sem GITHUB_TOKEN — apenas log):")
        print(f"    título: {titulo}")
        print(f"    labels: {labels}")
        print(f"    corpo:\n{corpo}")
        return False

    url = f"https://api.github.com/repos/{repo}/issues"
    req = urllib.request.Request(
        url,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        data=json.dumps({"title": titulo, "body": corpo,
                          "labels": labels}).encode(),
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            payload = json.loads(r.read())
            print(f"\n  ✓ Issue criada: {payload.get('html_url')}")
            return True
    except urllib.error.HTTPError as e:
        print(f"  ✗ Falha ao criar issue: {e}")
        return False


def _checklist_g1(prod: pd.DataFrame) -> str:
    ult = prod.tail(N_ULTIMAS)
    return f"""
**Gatilho disparado:** as últimas {N_ULTIMAS} previsões em produção
tiveram erro absoluto > {LIMITE_ERRO_PP:.1f} pp.

| Mês alvo | Previsto (pp) | Realizado (pp) | Erro abs. (pp) |
|---|---|---|---|
""" + "\n".join(
    f"| {r['mes_alvo'].strftime('%Y-%m')} | "
    f"{r['previsao_pontual']*100:+.2f} | "
    f"{r['realizado']*100:+.2f} | "
    f"{r['erro']*100:.2f} |"
    for _, r in ult.iterrows()
) + f"""

## Checklist de investigação

- [ ] Verificar se houve choque macroeconômico no período (COVID-like).
- [ ] Conferir se o snapshot do PIM-PF foi atualizado corretamente.
- [ ] Conferir se o snapshot ANTAQ tem cobertura completa do período.
- [ ] Reajustar o DFM com dados mais recentes (refit_anual.py --force).
- [ ] Avaliar se o lag estrutural -2 ainda se sustenta (rolling
      cross-correlation).
- [ ] Considerar antecipar o re-test de 2028.

Não modificar o status público do indicador sem decisão humana
documentada.
""".strip()


def _checklist_g2(cobertura: float, n: int) -> str:
    return f"""
**Gatilho disparado:** cobertura empírica acumulada em produção
fora da faixa [{COBERTURA_MIN:.0%}, {COBERTURA_MAX:.0%}] após {n}
previsões com realizado disponível.

- Cobertura observada: **{cobertura:.1%}**
- Limite inferior: {COBERTURA_MIN:.0%}
- Limite superior: {COBERTURA_MAX:.0%}

## Checklist de investigação

- [ ] Re-rodar calibração conformal com janela atual (split conformal padrão).
- [ ] Avaliar se block-bootstrap entrega cobertura mais próxima da nominal.
- [ ] Conferir se houve mudança estrutural (variância dos erros).
- [ ] Ampliar nota técnica do produto público com a observação atual.

Recalibração é a ação esperada — **não** rebaixamento automático.
""".strip()


def main() -> int:
    print("\n  ── verifica_degradacao ──")
    if not HIST.exists():
        print(f"  ✗ falta {HIST.relative_to(ROOT)}")
        return 1

    df = pd.read_csv(HIST, parse_dates=["mes_alvo", "data_emissao"])
    prod = df[(df["tipo"] == "producao") &
                df["realizado"].notna() & (df["realizado"] != "")].copy()
    prod = prod[pd.to_numeric(prod["realizado"], errors="coerce").notna()]
    if len(prod) == 0:
        print("  Nenhuma previsão em produção com realizado — sem alertas.")
        return 0

    prod["realizado"]        = pd.to_numeric(prod["realizado"])
    prod["erro"]             = pd.to_numeric(prod["erro"])
    prod["dentro_intervalo"] = prod["dentro_intervalo"].astype(str).str.lower() \
                                  .map({"true": True, "false": False, "nan": None})
    prod = prod.sort_values("mes_alvo")

    n_alertas = 0

    # G1: últimas 3 erros > 6 pp
    if len(prod) >= N_ULTIMAS:
        ult = prod.tail(N_ULTIMAS)
        if (ult["erro"] * 100 > LIMITE_ERRO_PP).all():
            titulo = (f"[Degradação] Últimas {N_ULTIMAS} previsões em "
                       f"produção com erro > {LIMITE_ERRO_PP:.0f} pp")
            corpo = _checklist_g1(ult)
            _abrir_issue(titulo, corpo, ["degradacao-modelo",
                                            "pim-pf-combinado",
                                            "auto-alerta"])
            n_alertas += 1

    # G2: cobertura fora da faixa após pelo menos N_MIN previsões
    n_with_cov = prod["dentro_intervalo"].notna().sum()
    if n_with_cov >= N_MIN_COBERTURA:
        cobertura = float(prod["dentro_intervalo"].dropna().mean())
        if not (COBERTURA_MIN <= cobertura <= COBERTURA_MAX):
            titulo = (f"[Cobertura] Empírica em {cobertura:.0%} "
                       f"(faixa esperada {COBERTURA_MIN:.0%}–{COBERTURA_MAX:.0%}, "
                       f"n={n_with_cov})")
            corpo = _checklist_g2(cobertura, n_with_cov)
            _abrir_issue(titulo, corpo, ["cobertura-fora-da-faixa",
                                            "pim-pf-combinado",
                                            "auto-alerta"])
            n_alertas += 1

    if n_alertas == 0:
        print(f"  Nenhum gatilho ativado. n_producao={len(prod)}, "
              f"último erro={prod['erro'].iloc[-1]*100:.2f} pp.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
