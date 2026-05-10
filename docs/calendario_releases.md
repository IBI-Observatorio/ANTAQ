# Calendário de releases — PIM-PF Combinado IBI

Janela: **mai/2026 → mai/2028** (re-test programado).

Cada linha representa um ciclo mensal completo do pipeline. Datas
nominais — pequenas variações (1–3 dias) são esperadas conforme o
calendário do IBGE para o PIM-PF.

| Mês ref. | IBGE PIM-PF publica | Cron pipeline (08h UTC) | Mês alvo h=2 | Status |
|---|---|---|---|---|
| 2026-03 | ~02/05/2026 | 05/05/2026 | 2026-05 | **Ensaio fechado** (URL não-divulgada) |
| 2026-04 | ~02/06/2026 | 05/06/2026 | 2026-06 | Ensaio fechado / divulgação pública |
| 2026-05 | ~02/07/2026 | 05/07/2026 | 2026-07 | **1ª previsão produção pública** |
| 2026-06 | ~02/08/2026 | 05/08/2026 | 2026-08 | Produção |
| 2026-07 | ~02/09/2026 | 05/09/2026 | 2026-09 | Produção · ≥ 2 previsões com realizado → liberar imprensa proativa |
| 2026-08 | ~02/10/2026 | 05/10/2026 | 2026-10 | Produção |
| 2026-09 | ~02/11/2026 | 05/11/2026 | 2026-11 | Produção |
| 2026-10 | ~02/12/2026 | 05/12/2026 | 2026-12 | Produção · ~6 previsões com realizado → métricas em produção começam a aparecer no card |
| 2026-11 | ~05/01/2027 | 05/01/2027 | 2027-01 | Produção · **Refit anual DFM-2027** (mesmo dia) |
| 2026-12 | ~02/02/2027 | 05/02/2027 | 2027-02 | Produção (DFM-2027) |
| 2027-01 | ~02/03/2027 | 05/03/2027 | 2027-03 | Produção |
| 2027-02 | ~02/04/2027 | 05/04/2027 | 2027-04 | Produção |
| ... | ... | ... | ... | ... |
| 2027-12 | ~05/01/2028 | 05/01/2028 | 2028-01 | Produção · **Refit anual DFM-2028** |
| 2028-01 | ~02/02/2028 | 05/02/2028 | 2028-02 | Produção |
| 2028-02 | ~02/03/2028 | 05/03/2028 | 2028-03 | Produção |
| 2028-03 | ~02/04/2028 | 05/04/2028 | 2028-04 | Produção · janela acumulada ≈ 24 meses de produção |
| **2028-05** | — | **alerta automático cron retest** | — | **Alerta humano para re-test completo** |

---

## Marcos importantes

### Release público — set/2026

Após ≥ 2 previsões em produção com realizado, considera-se autorizado
o **outreach proativo** a jornalistas (Valor Econômico, Folha de S.Paulo,
Estadão Economia). Antes disso, o indicador fica disponível no site,
mas não é ativamente divulgado.

### Métricas de produção começam a aparecer — dez/2026

Quando houver ≥ 6 previsões em produção com realizado, o card no site
deixa de mostrar "aguardando 6 previsões" e passa a renderizar:

- MAE rolling 12 meses em produção
- Cobertura empírica acumulada
- Comparação com MAE de validação histórica (3,01 pp)

### Refit anual — 5 de janeiro de cada ano

Cron `0 6 5 1 *` em `pipelines/pimpf_combinado/refit_anual.py`. Re-estima
DFM-1f com janela expansiva completa até dezembro do ano anterior. Não
sobrescreve modelos antigos (auditabilidade).

| Ano refit | Janela de treino | Status |
|---|---|---|
| 2026 | jan/2014 → dez/2025 | Em produção |
| 2027 | jan/2014 → dez/2026 | Programado |
| 2028 | jan/2014 → dez/2027 | Programado · alimenta re-test |

### Re-test mai/2028 — checkpoint metodológico

Conforme [`compromisso_retest_2028.md`](../validacao/portgdp_v2/compromisso_retest_2028.md):

- Cron `retest_pimpf_combinado.yml` dispara em mai/2028 com gate temporal.
- Apenas **abre issue com checklist** — não rebaixa automaticamente.
- Re-execução completa da bateria por equipe humana.
- Decisão pré-registrada: A/B (promove), D (mantém com ajuste), E (rebaixa).
- Publicação integral do resultado independentemente do veredito.

---

## Política de imprensa

- **Antes de set/2026**: nenhum outreach proativo. Indicador disponível
  no site mas não divulgado ativamente.
- **Set/2026 em diante**: outreach a 3–5 veículos econômicos selecionados,
  com material de imprensa pré-aprovado e link para nota técnica.
- **Em caso de erro grande em produção**: declarar publicamente,
  documentar no card, não tentar minimizar.
- **Em caso de degradação sistêmica**: pausar outreach e disparar
  discussão de re-test antecipado.

---

## Histórico de revisões deste calendário

| Data | Mudança | Autor |
|---|---|---|
| 2026-05-04 | Versão inicial — janela mai/2026 a mai/2028 | IBI |
