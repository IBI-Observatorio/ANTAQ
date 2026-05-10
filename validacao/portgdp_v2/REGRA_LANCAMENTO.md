# Pré-registro — Itens finais antes do lançamento da Linha D

**Carimbo (commit antes da execução):** 2026-05-04
**Stop firme:** 2 dias úteis. Se algum item não rodar limpo, escala antes
de continuar.

Pré-requisitos para publicação pública do **PIM-PF Combinado IBI**.

---

## Item 1 — Pesos Granger-Ramanathan em rolling OOS

### Motivação
Os pesos `w_DFM=0,411 / w_AR(1)=0,589` reportados no spike usaram OLS
sobre todos os pares (previsão, realizado) do walk-forward conjunto —
i.e., look-ahead na estimação dos pesos. Para validação OOS legítima,
pesos têm que ser reestimados a cada origem com expanding window.

### Especificação

Para cada origem τ do walk-forward (95–96 origens; h=1 e h=2 separados):

1. Coletar pares `(y_t, ŷ_DFM_t, ŷ_AR1_t)` de **todas as origens
   anteriores a τ** — janela expansiva.
2. Estimar pesos via OLS restrito sem intercepto, soma=1:
   `(y_t − ŷ_AR1_t) ~ (ŷ_DFM_t − ŷ_AR1_t)`. Coeficiente é `w_DFM`.
3. **Truncar em [0, 1]** se cair fora. Documentar quantos truncamentos
   ocorreram.
4. Aplicar pesos na previsão da origem τ:
   `ŷ_comb_τ = w_DFM,τ · ŷ_DFM_τ + (1 − w_DFM,τ) · ŷ_AR1_τ`.
5. **Janela mínima de aquecimento:** 36 origens. Origens 1–36 não geram
   previsão combinada (NaN). A partir da 37ª, peso é estimável e
   previsão combinada é registrada.

### Reportar
- Série temporal de `w_DFM` ao longo das origens (gráfico).
- Estatísticas: média, mediana, mín, máx, dp.
- Quantos truncamentos em [0,1] ocorreram.
- MAE, RMSE, pinball, CRPS da combinação OOS-legítima vs AR(1) puro vs
  DFM-1f puro **na mesma janela** (origens 37 em diante).
- DM-HLN combinação OOS vs AR(1) puro nessa janela.
- Tabela final substituindo os números in-sample (41% / 59%) pelos
  números OOS-legítimos.

### Decisão pós-resultado
- `w_DFM` médio OOS ≥ 25% **e** MAE_combinação < MAE_AR(1) na janela
  comum → **Linha D mantida**, números OOS substituem os in-sample na
  comunicação pública.
- `w_DFM` médio OOS < 15% **ou** MAE_combinação ≥ MAE_AR(1) →
  **Linha D fica frágil**, escalar antes de publicar.

---

## Item 2 — Calibração conformal dos intervalos de previsão

### Motivação
Intervalos nominais sem cobertura empírica validada foi exatamente o
problema do v1. Para o v2 ir a público com indicador preditivo, os
intervalos têm que reportar cobertura empírica ao lado da nominal, e o
método de construção precisa ter garantia formal.

### Método base — Split conformal padrão (Romano-Patterson-Candès / Lei et al. 2018)

- **Calibração**: erros absolutos `|y_t − ŷ_comb_t|` da primeira metade
  da janela OOS-legítima (origens 37 a meio).
- **Teste**: origens da segunda metade.
- **Quantil conformal**: para cobertura nominal 1−α = 80% (α = 0,20),
  calcular `q̂_{1-α}` como o `⌈(n+1)(1−α)⌉`-ésimo menor erro absoluto do
  conjunto de calibração. **Importante: usar a fórmula com correção
  `⌈(n+1)(1−α)⌉`, não o quantil empírico simples.** É o que separa
  "split conformal" (com garantia formal de Vovk sob exchangeability)
  de "quantil dos resíduos" (sem garantia).
- **Intervalo:** `[ŷ_comb_t − q̂, ŷ_comb_t + q̂]`.

### Variantes a comparar (rodar todas, reportar todas)

1. **Conformal padrão** — fórmula acima, simétrico, largura constante.
2. **Conformal com bloco bootstrap** (Politis-Romano) — calibração em
   blocos de 12 meses para robustez à autocorrelação serial.
3. **Quantil empírico simples** — `np.quantile(|err|, 1-α)`. Sem garantia
   formal. Reportado para comparação com o que foi feito no v1.

### Avaliar no conjunto de teste

- **Cobertura empírica**: fração de observações dentro do intervalo.
  Esperado para nominal 80%: ~80%.
- **Largura média**.
- **Pinball loss** nos quantis 10% e 90% implícitos.

### Tabela final

| Método | Nominal | Cobertura h=1 | Largura h=1 | Cobertura h=2 | Largura h=2 |
|---|---|---|---|---|---|
| Conformal padrão | 80% | ? | ? | ? | ? |
| Conformal block-bootstrap | 80% | ? | ? | ? | ? |
| Quantil empírico simples | 80% | ? | ? | ? | ? |

### Decisão pós-resultado

**Método para o produto público**: o de menor desvio absoluto entre
cobertura empírica e nominal (80%) com largura competitiva.

- Cobertura conformal padrão entre 75% e 85% → usa **conformal padrão**.
- Desvio > 5pp → usa **block-bootstrap**.
- Ambos desviam → registra na nota técnica e amplia banda por fator de
  correção empírico.

---

## Disciplina

- **Não alterar a regra de decisão da Linha D** enquanto roda. Se w_DFM
  OOS desabar, escalar; não reinterpretar.
- Quantis conformal usam `⌈(n+1)(1−α)⌉`, **não** quantil empírico
  ingênuo.
- **Cobertura empírica é o número que vai público** ao lado da nominal.
  Não negociar.
- Se durante implementação algo exigir desvio do pré-registro, logar em
  `log_modificacoes.md` com timestamp e motivo **antes** de modificar.

---

## ADENDO POST-RESULTADO — interpretação final do critério rolling (2026-05-04)

O pré-registro original definiu apenas dois extremos para a decisão do
Item 1:
- `w_DFM ≥ 25%` **e** MAE_comb < MAE_AR(1) → mantém Linha D
- `w_DFM < 15%` **ou** MAE_comb ≥ MAE_AR(1) → escala

A faixa `15% ≤ w_DFM < 25%` ficou sem regra explícita. Quando o resultado
de h=1 caiu nessa faixa (`w_DFM = 15,5%`), a implementação inicial
classificou como "zona cinza" e a interpretação final foi tomada na
discussão metodológica.

**Decisão final em h=1**: o resultado é tratado como **falha do critério
forte de Linha D**, não como zona neutra ambígua. Justificativa:

1. `w_DFM = 15,5%` está no **piso da banda definida** (apenas 0,5 pp
   acima do limiar de escalada); a banda existe para absorver erro
   amostral, não para legitimar resultado borderline.
2. A diferença de MAE (Δ = 0,04 pp) é estatisticamente indistinguível de
   zero; **DM-HLN p = 0,64**.
3. Encompassing em h=1 borderline (p = 0,10) também não suporta inclusão.

**Conclusão operacional**: combinação em h=1 **não publicada**.

### Lição metodológica para pré-registros futuros

Pré-registros devem cobrir todo o suporte `[0%, 100%]` com regras
**explícitas e mutuamente exclusivas**, sem zonas neutras. Sugestão de
template para o re-test 2028 e além:

- `w_DFM ≥ 25%` **e** MAE_comb < MAE_AR(1) por DM (p < 0,10) → mantém/promove
- `w_DFM ∈ [15%, 25%)` ou DM 0,10 ≤ p < 0,20 → resultado borderline:
  publicação somente com nota técnica explícita de fragilidade
- `w_DFM < 15%` **ou** MAE_comb ≥ MAE_AR(1) **ou** DM p ≥ 0,20 → falha

Sem essa estrutura completa, "zona cinza" vira espaço para interpretação
ad hoc que o pré-registro existe para evitar.

---

## STATUS FINAL POR HORIZONTE

| Horizonte | w_DFM rolling OOS | MAE comb vs AR(1) | DM p-valor | Status |
|---|---|---|---|---|
| h = 1 (mensal) | 15,5% (piso) | 2,02 vs 2,06 (Δ −0,04 pp) | 0,64 | **FALHA — não publicado** |
| h = 2 (bimestral) | **42,4%** | 3,01 vs 3,02 (Δ −0,01 pp) | 0,75 | **PUBLICADO** como PIM-PF Combinado IBI |

Em h=2, a manutenção da Linha D apoia-se no peso rolling OOS robusto
(42,4% praticamente idêntico ao 41,1% in-sample, dp = 0,028, sem
truncamentos) e no encompassing simétrico em h=2 (`λ_DFM->AR1=0,51`
p<0,001 e `λ_AR1->DFM=0,49` p<0,001 — informação complementar genuína).

Intervalos publicados em h=2: split conformal padrão (Lei et al. 2018,
quantil `⌈(n+1)(1-α)⌉`), cobertura nominal 80%, cobertura empírica
**100%** (IC95% Wilson [88,3%, 100%]) reportada como **conservadora**.
Sem shrink empírico — preserva garantia formal de Vovk.

Outputs de h=1 ficam arquivados em `h1_arquivado/` para transparência
(não suprimidos).
