# Log de modificações — PortGDP v2

Registro de qualquer desvio do pré-registro em `REGRA_DECISAO.md`.
Se nada foi alterado durante a execução, este arquivo permanece vazio
(salvo a entrada inicial).

---

## 2026-05-04 — abertura do log

Pré-registro consolidado. Início da execução do spike DFM v2.

## 2026-05-04 — fallback X-13 → STL

X-13 ARIMA-SEATS exige binário externo (Windows: not vendored com
statsmodels). Tentativa de execução resultou em falha imediata (binário
não encontrado). Aplicado fallback **STL** (`statsmodels.tsa.seasonal.STL`,
`period=12`, `robust=True`) em **todas as 35 séries**.

- Decisor: pré-registro original (cláusula "fallback documentado para STL")
- Justificativa: STL é o substituto pré-registrado; nenhum desvio do plano.
- Documentação: `dessaz_metodo.csv` lista o método aplicado por série
  (todas: `stl`).

Não há viés de seleção: STL foi aplicado uniformemente, não por série.

## 2026-05-04 — observações dos Itens 1 e 2 (lançamento)

Nenhum desvio do pré-registro foi necessário. Resultados executados conforme
REGRA_LANCAMENTO.md. Registro estas observações para a nota técnica:

**Item 1 (rolling GR OOS):**
- h=2: w_DFM médio OOS = 42,4% (in-sample foi 41,1%) — robustez do peso
  confirma sinal estrutural. 0 truncamentos em [0, 1] em ambos h.
- h=1: w_DFM médio OOS = 15,5%, abaixo do limiar de 25% pré-registrado.
- MAE da combinação supera AR(1) por margens minúsculas (0,01–0,04 pp em
  ambos h). DM não rejeita em nenhum h (p=0,64 e p=0,75). Sinal preditivo
  presente mas marginal — coerente com Linha D.

**Item 2 (calibração conformal):**
- h=1, conformal padrão: cobertura empírica 93,1%, IC Wilson 95%
  [78,0%, 98,1%] — **inclui 80% nominal**. Calibração estatisticamente
  válida em h=1.
- h=2, conformal padrão: cobertura 100%, IC [88,3%, 100%] — **não inclui
  80% nominal**. Sobrecobertura real (intervalos largos demais).
- Causa provável: n_teste = 29 é pequeno + caudas pesadas dos erros em h=2.
  Quantil de calibração captura tail event que não se materializa em 29
  pontos de teste.
- Block-bootstrap não melhora — pesa mais o tail event que o padrão.
- Decisão pré-registrada para "ambos desviam": aplicar conformal padrão
  com nota técnica explícita sobre cobertura conservadora em h=2.

**Limitação fundamental**: validação OOS-legítima reduz n efetivo a 58
origens (95 − 36 aquecimento). Split conformal divide em 29 calibração +
29 teste. Para estimar cobertura empírica com IC ≤ ±5 pp precisaria
n_teste ≥ ~150. Aceito a limitação por ser pré-registrada; reportar
explicitamente na comunicação pública que cobertura empírica é
estimada com IC amplo dada a janela disponível.

Nenhuma modificação feita à regra ou ao código que altere o resultado.
