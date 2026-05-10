# Compromisso de re-test — PortGDP v2

**Carimbo de pré-registro:** 2026-05-04
**Data alvo de execução:** maio/2028 (≈ 2 anos após o lançamento)
**Status atual do indicador:** Linha D, publicado apenas em h=2

---

## Por que pré-registrar agora

O **PIM-PF Combinado IBI** vai a público em 2026 sob status Linha D —
indicador descritivo com componente preditivo marginal validado. A
evidência atual é honesta mas tem dois pontos frágeis pré-registrados:

1. **Falta de poder estatístico**: a comparação por DM-HLN da combinação
   contra AR(1) puro tem p > 0,5 em h=2 (n=58 origens OOS-legítimas).
   Não rejeitar não é o mesmo que evidência de igualdade — pode ser que
   o sinal exista mas a janela disponível seja pequena demais para
   detectá-lo com poder ≥ 80%.
2. **Cobertura conformal acima da nominal em h=2**: empírica 100% vs
   nominal 80%, IC95% Wilson [88,3%, 100%]. Calibração funciona (sem
   sub-cobertura) mas é conservadora — n_teste=29 limita o que se pode
   afirmar sobre cobertura real.

O re-test em 2028 acrescenta **~24 origens novas** ao histórico
(jan/2026 a dez/2027 estimados ANTAQ + IBGE) — janela OOS-legítima passa
de ~58 para ~80, e n_teste do conformal de 29 para ~40-50. Aumento de
poder e calibração mais robusta.

---

## Bateria do re-test (idêntica à atual)

Reaproveitar **exatamente** o pipeline:

```
analises/validacao/portgdp_v2_dicionario.py        # mesmo dicionário 35 séries
analises/validacao/portgdp_v2_preparacao.py        # mesmo tratamento (X-13/STL + var12m)
analises/validacao/portgdp_v2_walkforward.py       # rolling-origin DFM-1f e DFM-2f
analises/validacao/portgdp_v2_decisao.py           # DM, encompassing, GR
analises/validacao/portgdp_v2_lancamento.py        # rolling GR OOS + conformal
```

Configurações pré-fixadas, **não alterar**:

- Top 10 portos pelo critério mecânico **2014-2026** (estende a janela
  de movimentação ainda mais para evitar que o ranking dependa de um
  único ano novo)
- 4 naturezas, 2 sentidos, `FlagLongoCurso=1`
- Filtro de cobertura: ≤24 meses zero/NA, sem streaks NaN >2
- DFM-1f (1 fator, AR(2)) **e** DFM-2f (2 fatores, VAR(1))
- Rolling-origin com `min_train=36`, h=1 e h=2 separados
- Baselines: AR(1), RW, sazonal_naive, ARDL
- DM-HLN com correção HLN, `α = 0,05` para os critérios
- Encompassing: convenção corrigida explícita
- GR rolling com `janela_aquecimento = 36`, truncamento [0, 1]
- Conformal padrão com `⌈(n+1)(1-α)⌉`, `α = 0,20` (cobertura nominal 80%)

**Critérios de decisão (regra completa, sem zonas mortas):**

- **Promoção para Linha A/B** se em h=2: DM da combinação rolling OOS vs
  AR(1) rejeitar H0 com p < 0,05 **e** w_DFM médio rolling permanecer
  ≥ 25%.
- **Manutenção da Linha D** se: w_DFM médio ≥ 25% **e** MAE_comb < MAE_AR(1)
  numericamente, mas DM ainda sem rejeição (0,05 ≤ p < 0,20).
- **Recalibração conformal** (sem mudar de linha) se a cobertura
  empírica desviar mais de 10 pp da nominal: aplicar block-bootstrap
  como produto público se ele entregar dentro de [70%, 90%]; caso
  contrário, ampliar nota técnica.
- **Rebaixamento para Linha E** se: w_DFM médio < 15% **ou**
  MAE_comb ≥ MAE_AR(1) **ou** DM p ≥ 0,20 sustentadamente.
- **Promoção em h=1** somente se *todos* os critérios da Linha D
  passarem em h=1 com folga (w_DFM ≥ 25%, DM p < 0,20, encompassing
  bilateral significativo).

> A regra acima cobre `[0%, 100%]` sem zonas mortas — lição metodológica
> aprendida no spike de 2026.

---

## Compromisso de publicação integral

**Independente do resultado em 2028**, o IBI compromete-se a:

1. Publicar o sumário executivo do re-test em
   `validacao/portgdp_v2/retest_2028/sumario_executivo.md` simultaneamente
   à atualização (ou rebaixamento) do indicador no observatório.
2. Manter os outputs CSV completos (rolling pesos, métricas, DM,
   encompassing, conformal) acessíveis.
3. Se houver **rebaixamento para Linha E**, comunicar publicamente no
   site do observatório com o motivo metodológico explícito —
   indicador é despublicado da landing como destaque, mantido em página
   secundária com nota retrospectiva.
4. Se houver **promoção para Linha A/B**, comunicar igualmente, com
   diff explícito do que mudou na evidência.
5. **Não** silenciosamente atualizar números do indicador sem o re-test
   formal entre 2026 e 2028.

Este compromisso reduz o incentivo a *p-hacking* implícito: o IBI não
pode escolher publicar só quando o resultado for favorável.

---

## Auditoria de mudanças no código entre 2026 e 2028

Qualquer alteração nos cinco scripts de validação listados acima entre
agora e a execução do re-test exige:

- Commit explícito antes do re-test, com PR (ou equivalente) descrevendo
  a alteração e o motivo
- Re-execução completa **antes** e **depois** da alteração, com
  comparação documentada do impacto nos números

Isso impede que ajustes sutis no pipeline sejam misturados com novos
dados — separação que é central para validação OOS legítima.

---

## Disparador automático — alerta humano, não rebaixamento

> **Correção pós-discussão metodológica (2026-05-04):** a versão inicial
> deste compromisso especificava rebaixamento automático para Linha E
> em mai/2028 caso o re-test não tivesse sido executado. Após revisão,
> isso foi **substituído por alerta humano**. O argumento é direto:
> rebaixamento é decisão sobre evidência. Cron não tem evidência —
> só tem calendário. Confundir os dois inverte a hierarquia entre
> automação e julgamento humano. O cron garante que o lembrete chega;
> a decisão sobre o status do indicador é do time IBI, com base em
> dados novos.

### O que o cron faz

Em **mai/2028**, um workflow agendado em
`.github/workflows/retest_pimpf_combinado.yml`:

1. **Abre uma issue** no repositório com título "Re-test PIM-PF
   Combinado IBI — devido em mai/2028" e o checklist completo do
   re-test (cobertura, baselines, DM, encompassing, GR rolling,
   conformal — copiado deste arquivo).
2. **Notifica a equipe IBI** (email/menção no GitHub) que o re-test
   está devido.
3. **Verifica** se `validacao/portgdp_v2/retest_2028/sumario_executivo.md`
   já existe; se não, registra na issue como pendente.
4. **NÃO modifica** o status do indicador no site, NÃO rebaixa para
   Linha E, NÃO altera nenhum arquivo de produção.

### O que rebaixa o indicador

**Apenas a re-execução da bateria completa por equipe humana**, com:

- Pull request explícito com os outputs novos do re-test
- Atualização do `metadata.py` e `c7_ineditas.py` refletindo a nova
  decisão (Linha A/B/C/D/E conforme regra)
- Atualização da nota técnica para versão 2 (`v2`) com diff em relação
  à v1
- Comunicação pública via post no observatório explicando a mudança

### Garantia operacional

A configuração do cron **faz parte do produto inicial** e é commitada
junto com este arquivo. Sem ela, o compromisso de re-test é apenas
declarativo. Com ela, o lembrete chega independentemente de turnover
de pessoal ou esquecimento — e a decisão fica onde deve: com humanos,
em frente a dados novos.
