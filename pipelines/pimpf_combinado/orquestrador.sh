#!/usr/bin/env bash
# Pipeline mensal PIM-PF Combinado IBI — sequência fetch → gera → atualiza → verifica.
#
# Idempotente: rodar duas vezes no mesmo dia não duplica linhas no
# histórico (a checagem é feita dentro de cada script).
#
# Uso:
#   bash pipelines/pimpf_combinado/orquestrador.sh
#   PULAR_ANTAQ=1 bash pipelines/pimpf_combinado/orquestrador.sh   # debug local
#
# Variáveis de ambiente reconhecidas (todas opcionais):
#   PULAR_ANTAQ   — se =1, não re-executa download_antaq.py
#   GH_REPO       — owner/repo para issues automáticas
#   GITHUB_TOKEN  — token para abrir issues
#   PYTHON        — interpretador Python (default: python)

set -euo pipefail

# Resolve raiz do repositório a partir do diretório do script
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python}"
DATA_HOJE="$(date -u +%Y-%m-%d)"
LOG_DIR="$ROOT/data/previsoes/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/orquestrador_$DATA_HOJE.log"

echo "═══════════════════════════════════════════════════════════════════"  | tee "$LOG"
echo "  PIM-PF Combinado IBI — pipeline mensal · $(date -u +'%Y-%m-%d %H:%M UTC')" | tee -a "$LOG"
echo "═══════════════════════════════════════════════════════════════════"  | tee -a "$LOG"

if [ "${PULAR_ANTAQ:-0}" = "1" ]; then
  EXTRA_FETCH="--pular-antaq"
  echo "  ⚠ PULAR_ANTAQ=1: pipeline ANTAQ não será re-executado." | tee -a "$LOG"
else
  EXTRA_FETCH=""
fi

# ─── Etapa 1: fetch dos snapshots ──────────────────────────────────────
echo
echo "▶ [1/4] fetch_dados.py"                                              | tee -a "$LOG"
"$PYTHON" -m pipelines.pimpf_combinado.fetch_dados $EXTRA_FETCH 2>&1 | tee -a "$LOG"

# ─── Etapa 2: gera previsão da origem corrente ─────────────────────────
echo
echo "▶ [2/4] gera_previsao.py"                                            | tee -a "$LOG"
"$PYTHON" -m pipelines.pimpf_combinado.gera_previsao 2>&1 | tee -a "$LOG"

# ─── Etapa 3: confronta com realizados ─────────────────────────────────
echo
echo "▶ [3/4] atualiza_realizados.py"                                      | tee -a "$LOG"
"$PYTHON" -m pipelines.pimpf_combinado.atualiza_realizados 2>&1 | tee -a "$LOG"

# ─── Etapa 4: verifica degradação ──────────────────────────────────────
echo
echo "▶ [4/4] verifica_degradacao.py"                                      | tee -a "$LOG"
"$PYTHON" -m pipelines.pimpf_combinado.verifica_degradacao 2>&1 | tee -a "$LOG"

echo
echo "═══════════════════════════════════════════════════════════════════"  | tee -a "$LOG"
echo "  ✓ orquestrador concluído · $(date -u +'%Y-%m-%d %H:%M UTC')"        | tee -a "$LOG"
echo "  Log completo: $LOG"                                                 | tee -a "$LOG"
echo "═══════════════════════════════════════════════════════════════════"  | tee -a "$LOG"
