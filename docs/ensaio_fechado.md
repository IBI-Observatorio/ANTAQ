# Ensaio fechado — PIM-PF Combinado IBI

> **Status:** aguardando definição de subdomínio.
> **Decisão pré-registrada:** ensaio fechado é **não-negociável**.
> Mesmo com release imediato decidido, as 2 semanas em URL
> não-divulgada acontecem antes da divulgação pública.

---

## Subdomínio / path — pendente de configuração

A infraestrutura atual do site (`ibi-observatorio.org`) é **GitHub Pages
estático** servido pelo repo `IBI-Observatorio/IBI-Observatorio`. Não tem
suporte nativo a subdomínios de preview separados. Três opções viáveis,
em ordem de preferência:

### Opção A — `ibi-observatorio.org/portos-preview/` (recomendada)

- **Como**: deploy de uma subpasta `dist/portos-preview/` com build
  específico do branch `producao/ensaio-fechado`. Acesso só por quem
  tem o link.
- **Vantagens**: zero infra adicional, mesma origem do site,
  cookies/CORS unificados.
- **Custo**: ~30 min de configuração no `vite.config.js` para suportar
  rota base diferente. Workflow GH Actions adicional para fazer build do
  branch `producao/ensaio-fechado` em `dist/portos-preview/`.

### Opção B — `pimpf-preview-ibi.netlify.app` (subdomínio Netlify gratuito)

- **Como**: criar app Netlify free (não custa nada), apontando para o
  branch `producao/ensaio-fechado` do repo. URL pública mas
  não-divulgada (off-the-record).
- **Vantagens**: zero invasão na infra atual; deploy automático em cada
  push no branch.
- **Custo**: criar conta Netlify (5 min), conectar repo (5 min). Requer
  que IBI tenha gestão da conta para pausar quando ensaio terminar.

### Opção C — `localhost` apenas, com link compartilhado por screenshot

- **Como**: roda `npm run dev` localmente, compartilha screenshots e
  vídeos da página renderizada com o time interno do IBI.
- **Vantagens**: zero infra. Total controle.
- **Desvantagens**: não permite teste de cron real ou validação cruzada
  de jornalistas convidados.

**Recomendação Claude Code**: opção A. Configurar `vite.config.js` para
suportar `base: '/portos-preview/'` e adicionar workflow GH Actions
`deploy_preview.yml` que builda o branch `producao/ensaio-fechado` em
`dist/portos-preview/` na produção (mesmo bucket, path separado).

**Decisão pendente do usuário**: qual opção adotar? Sem isso, ensaio
fechado roda em `localhost` (opção C) por padrão.

---

## Roteiro do ensaio (2 semanas)

Pré-condição: branch `producao/ensaio-fechado` existe com toda a
infraestrutura dos Blocos 1–5 implementada.

### Dia 0 — preparação

- [ ] Criar branch a partir de `main`: `git checkout -b producao/ensaio-fechado`
- [ ] Confirmar que `models/dfm_2026.pkl` existe (rodar
      `python -m pipelines.pimpf_combinado.refit_anual --ano 2026 --force` se necessário)
- [ ] Confirmar que `data/previsoes/historico.csv` está pré-populado
      (rodar `python -m pipelines.pimpf_combinado.popular_historico`)
- [ ] Rodar `bash pipelines/pimpf_combinado/orquestrador.sh` localmente e
      conferir que terminou sem erro
- [ ] Confirmar que `_publicar/indicadores/30-portgdp.json` tem os campos
      novos (`card_previsao_atual`, `track_record`, `metricas_producao`,
      `disclaimer_vintage`, `links_transparencia`)
- [ ] Sincronizar JSONs com o site: `cp -r _publicar/* "$SITE/public/data/antaq/"`
- [ ] Build local: `npm run build` (sem erros)
- [ ] Deploy do branch para a URL de preview (opção A, B ou C escolhida)

### Dias 1–7 — validação técnica

- [ ] Rodar `orquestrador.sh` 2–3 vezes manualmente. Confirmar idempotência:
      `historico.csv` não duplica linhas com mesma `(data_emissao, mes_alvo, horizonte, tipo)`.
- [ ] Inspecionar `data/snapshots/manifest.csv`: hashes diferentes para
      cada snapshot, n_observações coerente.
- [ ] Disparar cron mensal manualmente via `workflow_dispatch` do
      GitHub Actions. Confirmar que abre PR `data-update/AAAA-MM` com
      label `auto-merge-data`.
- [ ] Provocar falha (ex: variável de ambiente errada) e confirmar que o
      workflow abre issue `pipeline-falha`.
- [ ] Forçar gatilho de `verifica_degradacao.py` (manualmente injetar
      previsão com erro grande em ambiente de teste) e confirmar que
      issue é aberta.

### Dias 8–14 — validação visual

- [ ] Abrir URL de preview em desktop Chrome, Firefox e Safari mobile.
- [ ] Confirmar renderização de:
  - [ ] Badge "Linha D · validado · re-test mai/2028" no header
  - [ ] Subtítulo abaixo do título
  - [ ] **Card de Previsão atual** (vermelho, destacado, com IC 80%)
  - [ ] **Tabela Track record** com separação visual entre validação
        histórica (cinza) e produção (fundo vermelho-claro)
  - [ ] **Métricas em produção** (mensagem "aguardando 6 previsões"
        nas primeiras semanas)
  - [ ] **Disclaimer de vintage** em destaque âmbar, não escondido
  - [ ] **Bloco Transparência metodológica** com 3 links clicáveis
- [ ] Validar links — todos abrem corretamente nos 3 documentos:
  - [ ] `docs/nota_tecnica_pimpf_combinado_v1.md`
  - [ ] `validacao/portgdp_v2/h1_arquivado/README.md`
  - [ ] `validacao/portgdp_v2/compromisso_retest_2028.md`

### Dia 14 — checagem final + decisão

- [ ] Reunião de fechamento do ensaio com equipe IBI.
- [ ] Lista de bugs/ajustes encontrados → corrigir antes do merge.
- [ ] Aprovação formal de cada item da checklist do **Bloco 7
      "Disciplina"** do briefing original.
- [ ] **Se aprovado**: merge `producao/ensaio-fechado → main`. Deploy
      vai automaticamente para produção via GitHub Pages.
- [ ] Post no LinkedIn institucional do IBI anunciando o lançamento
      (texto do post pré-aprovado em `docs/post_lancamento_linkedin.md` —
      a ser criado).
- [ ] **Imprensa proativa: não fazer ainda.** Aguardar pelo menos
      2 previsões em produção com realizado disponível (≈ set/2026).

---

## Critérios de stop firme do ensaio

Encerrar o ensaio e **não fazer merge** se:

1. Pipeline falha em mais de 1 das 3 execuções manuais sem causa identificada.
2. Idempotência do `orquestrador.sh` quebra (CSV duplica linhas).
3. JSON do site fica inválido depois de uma execução do pipeline.
4. Algum dos 3 links de transparência fica quebrado em qualquer
   navegador testado.
5. Disclaimer de vintage fica escondido (ex: cor muito tênue, fora do
   viewport mobile).
6. Tabela de track record não distingue visualmente validação histórica
   de produção.

Em qualquer um desses casos, escala para discussão metodológica e a
implementação volta para a etapa de revisão antes de tentar de novo.

---

## Checklist de comunicação interna durante o ensaio

- [ ] Equipe IBI sabe da URL de preview e do prazo de 2 semanas.
- [ ] Ninguém compartilha a URL fora do IBI durante o ensaio.
- [ ] Bugs reportados via issue no repo (não Slack ou WhatsApp) para
      ter rastro auditável.
- [ ] Cada bug fechado tem PR vinculado.
- [ ] Issue de "ensaio fechado iniciado" é aberta no Dia 0 e fechada
      no Dia 14, listando tudo que foi validado.
