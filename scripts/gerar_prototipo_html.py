"""Gera HTML protótipo standalone (Plotly CDN) com os 3 indicadores do dashboard."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "dashboard"
OUT = Path(r"C:\Users\bruno\Documents\Claude\Hidrovias\hidrovia-dashboard\tmp_curvas\prototipo-medias-moveis.html")
OUT.parent.mkdir(parents=True, exist_ok=True)

embed = {
    "series":     json.load(open(D/"series_mensais.json",  encoding="utf-8")),
    "rotas":      json.load(open(D/"rotas.json",           encoding="utf-8")),
    "portos":     json.load(open(D/"portos.json",          encoding="utf-8")),
    "forecast":   json.load(open(D/"forecast.json",        encoding="utf-8")),
    "granel_liq": json.load(open(D/"granel_liquido.json",  encoding="utf-8")),
    "kpis":       json.load(open(D/"kpis.json",            encoding="utf-8")),
    "meta":       json.load(open(D/"meta.json",            encoding="utf-8")),
}

TEMPLATE = r"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Observatório do portuário brasileiro · Protótipo</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<script src="https://cdn.tailwindcss.com"></script>
<style>
  body { background:#111827; color:#e5e7eb; font-family: 'Inter', ui-sans-serif, system-ui, -apple-system, sans-serif; }
  .card { background:#2c2c2c; border:1px solid rgba(255,255,255,0.1); border-radius:1rem; }
  .eyebrow { font-size:.75rem; font-weight:600; text-transform:uppercase; letter-spacing:.08em; }
  .plot { width:100%; height:480px; }
  .plot-sm { width:100%; height:340px; }
  .kpi-num { font-feature-settings:"tnum"; font-variant-numeric:tabular-nums; }
  .kpi-legenda { font-size:.65rem; color:#6b7280; margin-top:.4rem;
                  letter-spacing:.03em; line-height:1.3; }
  select, button { background:#374151; border:1px solid #4b5563; color:#e5e7eb;
                    padding:.35rem .7rem; border-radius:.4rem; font-size:.85rem; }
  select:hover, button:hover { background:#4b5563; }
  .pill { display:inline-block; padding:.15rem .5rem; border-radius:9999px;
          font-size:.7rem; font-weight:600; }
  .achado { display:flex; gap:.5rem; align-items:flex-start; }
  .achado-bullet { color:#0099D8; font-weight:bold; }
</style>
</head>
<body>

<header class="sticky top-0 z-50" style="background:#2c2c2c;">
  <div class="container mx-auto px-6 py-4 flex items-center justify-between">
    <div>
      <div class="text-xs text-gray-400 uppercase tracking-wider">Observatório IBI · Protótipo</div>
      <div class="text-lg font-semibold text-white">Observatório do portuário brasileiro · três lentes sobre 15 anos de movimentação</div>
    </div>
    <div class="text-xs text-gray-400 text-right">
      <div>Última atualização ANTAQ:</div>
      <div class="text-gray-200" id="ultimo-mes"></div>
    </div>
  </div>
</header>

<section class="container mx-auto px-6 mt-8">
  <div class="grid grid-cols-2 md:grid-cols-4 gap-4">

    <div class="card p-4">
      <div class="text-xs text-gray-400">Movimentação total Brasil</div>
      <div class="kpi-num text-2xl font-bold text-white mt-1" id="kpi-total"></div>
      <div class="text-xs mt-1" id="kpi-total-yoy"></div>
      <div class="kpi-legenda" id="kpi-total-legenda"></div>
    </div>

    <div class="card p-4">
      <div class="text-xs text-gray-400">Cabotagem (toneladas)</div>
      <div class="kpi-num text-2xl font-bold text-white mt-1" id="kpi-cab"></div>
      <div class="text-xs mt-1 text-gray-400" id="kpi-cab-off"></div>
      <div class="kpi-legenda" id="kpi-cab-legenda"></div>
    </div>

    <div class="card p-4">
      <div class="text-xs text-gray-400">Contêineres movimentados</div>
      <div class="kpi-num text-2xl font-bold text-white mt-1" id="kpi-teu"></div>
      <div class="text-xs mt-1 text-gray-400">Em TEUs (twenty-foot equivalent units)</div>
      <div class="kpi-legenda" id="kpi-teu-legenda"></div>
    </div>

    <div class="card p-4">
      <div class="text-xs text-gray-400">Crescimento granel líquido</div>
      <div class="kpi-num text-2xl font-bold text-white mt-1" id="kpi-mom"></div>
      <div class="text-xs mt-1 text-gray-400">Vs. mesmo período ano anterior</div>
      <div class="kpi-legenda" id="kpi-mom-legenda"></div>
    </div>

  </div>
</section>

<!-- ─────────────────────── INDICADOR 31 ─────────────────────── -->
<section class="container mx-auto px-6 mt-12">
  <div class="card p-6">
    <div class="flex items-baseline justify-between mb-2">
      <div>
        <div class="eyebrow" style="color:#0099D8">31 · Tendência por carga</div>
        <h2 class="text-2xl font-bold text-white mt-1">Para onde vai a movimentação dos portos brasileiros?</h2>
      </div>
      <div class="pill" style="background:#0099D820;color:#0099D8">ineditas</div>
    </div>
    <p class="text-gray-400 mt-2 text-sm max-w-3xl leading-relaxed">
      Uma <strong>projeção de 5 meses à frente</strong> para o ritmo do contêiner,
      calibrada pela atividade econômica do país (IBC-Br do BCB).
      Em seguida, o contexto histórico de 15 anos que sustenta essa leitura.
    </p>

    <div class="mt-6">
      <div class="text-base text-white font-semibold mb-1">E o que vem pelos próximos meses?</div>
      <p class="text-xs text-gray-400 mb-3 leading-relaxed max-w-3xl">
        Projeção do ritmo do contêiner usando um modelo simples calibrado com dois sinais antecedentes:
        a atividade econômica geral (IBC-Br do Banco Central) e o ritmo da carga geral 12 meses antes.
        A faixa cinza-avermelhada é a margem de erro típica.
        <span id="ind31-modelo-meta"></span>
      </p>
      <div id="ind31-forecast" class="plot-sm"></div>
    </div>

    <div class="mt-10 border-t border-gray-700 pt-6">
      <div class="text-base text-white font-semibold mb-3">Contexto histórico: 15 anos de médias móveis por carga</div>

      <div class="mt-4 grid md:grid-cols-2 gap-x-6 gap-y-2 max-w-3xl">
        <div class="achado text-xs text-gray-300">
          <span class="achado-bullet">●</span>
          <span><strong style="color:#00A652">Granel sólido</strong> (soja, milho, minério) cresce <span id="achado-gs-mom">+7%</span> ao ano,
                puxado pela safra recorde e pelo arco norte.</span>
        </div>
        <div class="achado text-xs text-gray-300">
          <span class="achado-bullet" style="color:#c1322f">●</span>
          <span><strong style="color:#c1322f">Granel líquido</strong> (petróleo, combustíveis) acelera <span id="achado-gl-mom">11%</span> a/a
                com o pré-sal exportando a todo vapor.</span>
        </div>
        <div class="achado text-xs text-gray-300">
          <span class="achado-bullet" style="color:#D4922A">●</span>
          <span><strong style="color:#D4922A">Carga geral</strong> (mercadorias em pallets, sacos, fardos)
                <span id="achado-cg-status">cai 3%</span>.</span>
        </div>
        <div class="achado text-xs text-gray-300">
          <span class="achado-bullet">●</span>
          <span><strong style="color:#0099D8">Contêiner</strong> segue crescendo (<span id="achado-ct-mom">+5%</span>),
                com ritmo a confirmar nos próximos meses.</span>
        </div>
      </div>

      <div class="mt-5 flex flex-wrap items-center gap-3">
        <label class="text-xs text-gray-400">Como medir:</label>
        <select id="ind31-metrica">
          <option value="ma12_mt">Volume mensal médio (em milhões de toneladas)</option>
          <option value="indice100">Quanto cresceu desde jan/2011 (base = 100)</option>
          <option value="yoy_ma_pct">Crescimento ano contra ano (%)</option>
        </select>
        <button id="ind31-reset" class="ml-auto">Voltar ao zoom inicial</button>
      </div>

      <div id="ind31-plot" class="plot mt-4"></div>
    </div>
  </div>
</section>

<!-- ─────────────────────── INDICADOR 32 ─────────────────────── -->
<section class="container mx-auto px-6 mt-8">
  <div class="card p-6">
    <div class="flex items-baseline justify-between mb-2">
      <div>
        <div class=”eyebrow” style=”color:#00A652”>32 · Cabotagem</div>
        <h2 class=”text-2xl font-bold text-white mt-1”>Quase metade da “cabotagem” brasileira é petróleo do pré-sal</h2>
      </div>
      <div class=”pill” style=”background:#00A65220;color:#00A652”>cabotagem-hidrovias</div>
    </div>
    <p class="text-gray-400 mt-2 text-sm max-w-3xl leading-relaxed">
      Quando a ANTAQ fala em “cabotagem”, junta duas coisas muito diferentes:
      <strong>cargas indo de um porto brasileiro a outro</strong> (a cabotagem que todo mundo imagina) e
      <strong>petróleo bombeado de plataformas offshore</strong> (FPSO, na Zona Econômica Exclusiva) para o continente.
      Separamos as duas para revelar qual é o tamanho real da cabotagem doméstica.
    </p>

    <div class="mt-4 grid md:grid-cols-2 gap-x-6 gap-y-2 max-w-3xl">
      <div class="achado text-xs text-gray-300">
        <span class="achado-bullet" style="color:#00A652">●</span>
        <span><strong>Cabotagem doméstica</strong>: cerca de <span id="achado-cab-dom">163 Mt</span>/ano, com crescimento moderado.</span>
      </div>
      <div class="achado text-xs text-gray-300">
        <span class="achado-bullet" style="color:#c1322f">●</span>
        <span><strong>Petróleo offshore (FPSO/ZEE)</strong>: <span id="achado-cab-off">144 Mt</span>/ano — vetor do pré-sal em expansão.</span>
      </div>
      <div class="achado text-xs text-gray-300">
        <span class="achado-bullet" style="color:#c1322f">●</span>
        <span>Quase metade <strong>(<span id="achado-cab-pct">46,9%</span>)</strong> do total contabilizado como cabotagem é offshore.</span>
      </div>
      <div class="achado text-xs text-gray-300">
        <span class="achado-bullet">●</span>
        <span><strong>Maior rota do país</strong>: Manaus → Santos com contêineres da Zona Franca.</span>
      </div>
    </div>

    <div class="grid lg:grid-cols-5 gap-6 mt-5">
      <div class="lg:col-span-2">
        <div class="text-xs text-gray-400 mb-2">Volume anual da cabotagem brasileira (Mt)</div>
        <div id="ind32-stack" class="plot-sm"></div>
        <div class="kpi-legenda mt-2">Soma móvel de 12 meses · cada ponto = total acumulado dos 12 meses anteriores</div>
      </div>
      <div class="lg:col-span-3">
        <div class="flex items-center justify-between mb-2">
          <div class="text-xs text-gray-400">Maiores rotas de contêiner entre portos brasileiros</div>
          <select id="ind32-rotas-top">
            <option value="10">Top 10</option>
            <option value="20">Top 20</option>
            <option value="30">Top 30</option>
          </select>
        </div>
        <div id="ind32-rotas" class="plot-sm"></div>
        <div class="kpi-legenda mt-2">
          Total de contêineres movimentados em cada rota desde 2010 ·
          rótulo ao lado da barra = crescimento médio anual (CAGR)
        </div>
      </div>
    </div>
  </div>
</section>

<!-- ─────────────────────── INDICADOR 33 ─────────────────────── -->
<section class="container mx-auto px-6 mt-8 mb-16">
  <div class="card p-6">
    <div class="flex items-baseline justify-between mb-2">
      <div>
        <div class="eyebrow" style="color:#D4922A">33 · Geografia</div>
        <h2 class="text-2xl font-bold text-white mt-1">Quais portos estão ganhando — ou perdendo — espaço no mercado?</h2>
      </div>
      <div class="pill" style="background:#D4922A20;color:#D4922A">infraestrutura</div>
    </div>
    <p class="text-gray-400 mt-2 text-sm max-w-3xl leading-relaxed">
      Cada tipo de carga tem um ritmo nacional de crescimento — esse é o seu “mercado”.
      Aqui você vê portos individuais comparados com essa média nacional.
      Quem cresceu <strong>acima</strong> da média ganhou espaço (roubou movimento dos concorrentes);
      quem cresceu <strong>abaixo</strong> perdeu espaço. Análise cobre 2018 até o último ano fechado,
      considerando apenas portos com volume relevante (≥ 0,5 milhão de toneladas por ano).
    </p>

    <div class="mt-4 grid md:grid-cols-2 gap-x-6 gap-y-2 max-w-3xl">
      <div class="achado text-xs text-gray-300">
        <span class="achado-bullet" style="color:#00A652">●</span>
        <span><strong>Porto do Açu (RJ)</strong> cresce 29% ao ano no granel líquido —
              quase dobrou de tamanho com o pré-sal.</span>
      </div>
      <div class="achado text-xs text-gray-300">
        <span class="achado-bullet" style="color:#00A652">●</span>
        <span><strong>Ponta Ubu (ES)</strong> virou a casa no granel sólido —
              minério voltou ao Espírito Santo após Brumadinho.</span>
      </div>
      <div class="achado text-xs text-gray-300">
        <span class="achado-bullet" style="color:#c1322f">●</span>
        <span><strong>Itajaí (SC)</strong> perde contêiner para <strong>Itapoá</strong>,
              um porto novo a 30 km de distância.</span>
      </div>
      <div class="achado text-xs text-gray-300">
        <span class="achado-bullet" style="color:#c1322f">●</span>
        <span><strong>Portocel (ES)</strong> cai 4% — celulose foi direto para o exterior,
              não usa mais cabotagem entre portos.</span>
      </div>
    </div>

    <div class="mt-5 flex flex-wrap items-center gap-3">
      <label class="text-xs text-gray-400">Tipo de carga:</label>
      <select id="ind33-natureza">
        <option value="granel_solido">Granel sólido (soja, milho, minério...)</option>
        <option value="granel_liquido">Granel líquido (petróleo, combustível...)</option>
        <option value="carga_geral">Carga geral (pallets, fardos, máquinas...)</option>
        <option value="conteinerizada">Carga conteinerizada</option>
      </select>
    </div>

    <p class="mt-4 text-sm text-gray-200" id="ind33-headline"></p>

    <div id="ind33-plot" class="plot mt-3"></div>

    <div class="kpi-legenda mt-2">
      Linha tracejada dourada = crescimento médio nacional dessa carga ·
      barra verde = porto cresceu acima dessa média (ganhou espaço) ·
      barra vermelha = porto cresceu abaixo (perdeu espaço) ·
      rótulo ao lado da barra = crescimento médio anual + volume movimentado no último ano
    </div>
  </div>
</section>

<footer class="border-t border-gray-800 mt-8 py-6 text-center text-xs text-gray-500">
  Protótipo do Observatório do Portuário Brasileiro · 3 análises sobre 15 anos da Estatística Aquaviária da ANTAQ
  <br>Fonte primária: ANTAQ (atualização mensal) · cruzamentos com BCB SGS (IBC-Br, PIB, câmbio)
</footer>

<script id="payload" type="application/json">__PAYLOAD__</script>
<script>
const PAYLOAD = JSON.parse(document.getElementById("payload").textContent);

const CORES = {
  granel_solido:        '#00A652',
  granel_liquido:       '#c1322f',
  carga_geral:          '#D4922A',
  conteinerizada:       '#0099D8',
  cabotagem_domestica:  '#00A652',
  offshore:             '#c1322f',
};
const LABELS = {
  granel_solido:        'Granel Sólido',
  granel_liquido:       'Granel Líquido e Gasoso',
  carga_geral:          'Carga Geral',
  conteinerizada:       'Carga Conteinerizada',
};
const MESES = ['jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez'];

function formatYM(ym) {
  if (!ym) return '';
  const [y, m] = ym.split('-');
  return MESES[+m - 1] + '/' + y.slice(2);
}
function formatYMlongo(ym) {
  if (!ym) return '';
  const [y, m] = ym.split('-');
  return MESES[+m - 1] + '/' + y;
}
function janela12m(ultimoYm) {
  // ultimo mês inclusivo. Janela = (ultimo - 11 meses) até ultimo
  const [y, m] = ultimoYm.split('-').map(Number);
  const ini = new Date(y, m - 12, 1);
  const ini_y = ini.getFullYear(), ini_m = ini.getMonth() + 1;
  return MESES[ini_m - 1] + '/' + String(ini_y).slice(2) + ' – ' + MESES[m - 1] + '/' + String(y).slice(2);
}

const layoutBase = {
  paper_bgcolor: '#2c2c2c',
  plot_bgcolor:  '#2c2c2c',
  font: { color: '#e5e7eb', family:'ui-sans-serif, system-ui', size: 12 },
  margin: { l:60, r:30, t:20, b:50 },
  xaxis: { gridcolor:'#374151', zerolinecolor:'#374151', tickfont:{ color:'#9ca3af' } },
  yaxis: { gridcolor:'#374151', zerolinecolor:'#374151', tickfont:{ color:'#9ca3af' } },
  hovermode: 'x unified',
  hoverlabel: { bgcolor:'#111827', bordercolor:'#4b5563', font:{ color:'#e5e7eb' } },
  legend: { orientation:'h', y:-0.15, x:0, font:{ color:'#d1d5db' } },
};
const config = { responsive:true, displaylogo:false,
                 modeBarButtonsToRemove:['lasso2d','select2d','autoScale2d'],
                 toImageButtonOptions:{ format:'png', filename:'observatorio-portuario' } };

// ─── Computar KPIs CONSISTENTES a partir de series_mensais ────────────────
function computarKPIs() {
  const series = PAYLOAD.series;
  const NATUREZAS = ['granel_solido','granel_liquido','carga_geral','conteinerizada'];

  // último mês com dado completo (último mês de natureza:granel_solido)
  const granelSolido = series.filter(r => r.serie === 'natureza:granel_solido' && r.sum12_mt != null)
                              .sort((a,b) => a.data.localeCompare(b.data));
  const ultMes = granelSolido[granelSolido.length - 1].data;

  // Total Brasil em 12m = soma dos sum12_mt de cada natureza no último mês
  let totalSum12 = 0;
  let totalSum12Anterior = 0;
  for (const nat of NATUREZAS) {
    const sub = series.filter(r => r.serie === 'natureza:' + nat).sort((a,b)=>a.data.localeCompare(b.data));
    const atual = sub.find(r => r.data === ultMes);
    if (atual && atual.sum12_mt != null) totalSum12 += atual.sum12_mt;
    // mesmo mês um ano antes
    const [y,m] = ultMes.split('-').map(Number);
    const anteriorYm = String(y-1) + '-' + String(m).padStart(2,'0');
    const anterior = sub.find(r => r.data === anteriorYm);
    if (anterior && anterior.sum12_mt != null) totalSum12Anterior += anterior.sum12_mt;
  }
  const totalYoy = totalSum12Anterior > 0 ? (totalSum12 / totalSum12Anterior - 1) * 100 : null;

  // Cabotagem (doméstica + offshore)
  const cabDom = series.filter(r => r.serie === 'cabotagem:cabotagem_domestica' && r.data === ultMes)[0];
  const cabOff = series.filter(r => r.serie === 'cabotagem:offshore' && r.data === ultMes)[0];
  const cabTotal = (cabDom?.sum12_mt || 0) + (cabOff?.sum12_mt || 0);
  const cabOffPct = cabTotal > 0 ? (cabOff?.sum12_mt || 0) / cabTotal * 100 : null;

  // TEU
  const teuCab = series.filter(r => r.serie === 'teu:cabotagem' && r.data === ultMes)[0];
  const teuLc  = series.filter(r => r.serie === 'teu:longo_curso' && r.data === ultMes)[0];
  const teuTotal = (teuCab?.sum12_teu || 0) + (teuLc?.sum12_teu || 0);

  // Momentum granel líquido
  const liqUlt = series.filter(r => r.serie === 'natureza:granel_liquido' && r.data === ultMes)[0];

  return {
    ultMes,
    totalSum12,
    totalYoy,
    cabTotal,
    cabOffPct,
    teuTotal,
    momentumLiquido: liqUlt?.yoy_ma_pct,
  };
}

const K = computarKPIs();
document.getElementById('ultimo-mes').textContent = formatYMlongo(PAYLOAD.meta.ultimo_mes_dados);

document.getElementById('kpi-total').textContent = fmt(K.totalSum12, 0) + ' Mt';
const yoyCor = K.totalYoy >= 0 ? '#00A652' : '#c1322f';
document.getElementById('kpi-total-yoy').innerHTML =
  '<span style="color:' + yoyCor + '">' + (K.totalYoy >= 0 ? '▲' : '▼') + ' ' + Math.abs(K.totalYoy).toFixed(2) + '% vs. 12 meses anteriores</span>';
document.getElementById('kpi-total-legenda').textContent = 'Soma de 12 meses · ' + janela12m(K.ultMes);

document.getElementById('kpi-cab').textContent = fmt(K.cabTotal, 0) + ' Mt';
document.getElementById('kpi-cab-off').textContent = K.cabOffPct.toFixed(1) + '% é petróleo offshore (FPSO/ZEE)';
document.getElementById('kpi-cab-legenda').textContent = 'Soma de 12 meses · ' + janela12m(K.ultMes);

document.getElementById('kpi-teu').textContent = (K.teuTotal / 1e6).toFixed(2) + ' M';
document.getElementById('kpi-teu-legenda').textContent = 'Soma de 12 meses · ' + janela12m(K.ultMes);

document.getElementById('kpi-mom').textContent = (K.momentumLiquido >= 0 ? '+' : '') + K.momentumLiquido.toFixed(2) + '%';
document.getElementById('kpi-mom-legenda').textContent =
  'Variação da média de 12 meses · ' + janela12m(K.ultMes) + ' vs. mesmo período do ano anterior';

// ─── Achados dinâmicos ────────────────────────────────────────────────────
const mom = PAYLOAD.kpis.momentum_atual || {};
const fmtMom = v => v == null ? '—' : (v >= 0 ? '+' : '') + Math.abs(v).toFixed(1) + '%';
const gsEl = document.getElementById('achado-gs-mom');
const glEl = document.getElementById('achado-gl-mom');
const cgEl = document.getElementById('achado-cg-status');
const ctEl = document.getElementById('achado-ct-mom');
if (gsEl) gsEl.textContent = fmtMom(mom.granel_solido) + ' a/a';
if (glEl) glEl.textContent = Math.abs(mom.granel_liquido || 0).toFixed(0) + '% a/a';
if (cgEl) {
  const cgV = mom.carga_geral;
  cgEl.textContent = cgV == null ? '—' : (cgV < 0 ? 'cai ' + Math.abs(cgV).toFixed(0) + '%' : 'cresce ' + cgV.toFixed(0) + '%');
}
if (ctEl) ctEl.textContent = fmtMom(mom.conteinerizada);

// Achados cabotagem (usa K já calculado)
const cabDomEl = document.getElementById('achado-cab-dom');
const cabOffEl = document.getElementById('achado-cab-off');
const cabPctEl = document.getElementById('achado-cab-pct');
const cabOffMt = K.cabTotal > 0 ? K.cabTotal * K.cabOffPct / 100 : 0;
const cabDomMt = K.cabTotal - cabOffMt;
if (cabDomEl) cabDomEl.textContent = fmt(cabDomMt, 0) + ' Mt';
if (cabOffEl) cabOffEl.textContent = fmt(cabOffMt, 0) + ' Mt';
if (cabPctEl) cabPctEl.textContent = K.cabOffPct.toFixed(1) + '%';

// ─── INDICADOR 31 ────────────────────────────────────────────────────────
const NATUREZAS = ['granel_solido','granel_liquido','carga_geral','conteinerizada'];

function seriesPorNatureza(metrica) {
  const out = [];
  for (const nat of NATUREZAS) {
    const sId = 'natureza:' + nat;
    const sub = PAYLOAD.series.filter(r => r.serie === sId)
                              .sort((a,b) => a.data.localeCompare(b.data));
    let valor;
    if (metrica === 'indice100') {
      const base = sub.find(r => r.ma12_mt != null)?.ma12_mt;
      valor = sub.map(r => r.ma12_mt != null ? r.ma12_mt / base * 100 : null);
    } else {
      valor = sub.map(r => r[metrica]);
    }
    out.push({
      x: sub.map(r => r.data + '-01'),
      y: valor,
      name: LABELS[nat],
      mode: 'lines',
      line: { color: CORES[nat], width: 2.2 },
      hovertemplate: '%{y:,.2f}<extra></extra>',
    });
  }
  return out;
}
function plotInd31(metrica) {
  const data = seriesPorNatureza(metrica);
  const titulos = { ma12_mt:'Milhões de toneladas/mês (média móvel 12m)',
                    indice100:'Índice base 100 (jan/2011 = 100)',
                    yoy_ma_pct:'Crescimento ano contra ano (%)' };
  const layout = { ...layoutBase, yaxis: { ...layoutBase.yaxis, title:{ text:titulos[metrica], font:{ color:'#9ca3af' } } } };
  if (metrica === 'indice100') layout.shapes = [{ type:'line', xref:'paper', x0:0, x1:1, y0:100, y1:100,
                                                    line:{ color:'#9ca3af', width:1, dash:'dash' } }];
  if (metrica === 'yoy_ma_pct') layout.shapes = [{ type:'line', xref:'paper', x0:0, x1:1, y0:0, y1:0,
                                                    line:{ color:'#9ca3af', width:1, dash:'dash' } }];
  Plotly.react('ind31-plot', data, layout, config);
}
plotInd31('ma12_mt');
document.getElementById('ind31-metrica').addEventListener('change', e => plotInd31(e.target.value));
document.getElementById('ind31-reset').addEventListener('click', () =>
  Plotly.relayout('ind31-plot', { 'xaxis.autorange':true, 'yaxis.autorange':true }));

// Forecast contêiner — versão simplificada
const f = PAYLOAD.forecast;
const ult_obs_data = f.serie[f.serie.length - 1]?.data;
document.getElementById('ind31-modelo-meta').innerHTML =
  ' Modelo simples (regressão linear) explica cerca de ' + Math.round((f.modelo.r2_oos || 0) * 100) +
  '% da variação fora da amostra de treino. Correlação entre projeção e observação: ' +
  (f.modelo.corr_oos || 0).toFixed(2) + '.';
const fc = f.forecast || [];
const traceObs   = { x: f.serie.map(r => r.data+'-01'), y: f.serie.map(r => r.observado),
                      name:'Observado (contêiner)', mode:'lines', line:{ color:'#0099D8', width:2.4 } };
const tracePred  = { x: f.serie.map(r => r.data+'-01'), y: f.serie.map(r => r.predito),
                      name:'Calculado pelo modelo', mode:'lines', line:{ color:'#9ca3af', width:1.4, dash:'dot' } };
const traceFc    = { x: fc.map(r => r.data+'-01'), y: fc.map(r => r.central_pct),
                      name:'Projeção (5 meses à frente)', mode:'lines+markers', line:{ color:'#D4922A', width:2.4 } };
const traceBand  = { x: [...fc.map(r=>r.data+'-01'), ...fc.map(r=>r.data+'-01').reverse()],
                      y: [...fc.map(r=>r.high_pct), ...fc.map(r=>r.low_pct).reverse()],
                      fill:'toself', fillcolor:'rgba(212,146,42,0.18)',
                      line:{ color:'rgba(0,0,0,0)' }, name:'Margem de erro', hoverinfo:'skip' };
Plotly.react('ind31-forecast', [traceObs, tracePred, traceBand, traceFc], {
  ...layoutBase,
  shapes: [{ type:'line', xref:'paper', x0:0, x1:1, y0:0, y1:0,
              line:{ color:'#6b7280', width:1, dash:'dash' } }],
  yaxis: { ...layoutBase.yaxis, title:{ text:'Crescimento ano contra ano (%)', font:{ color:'#9ca3af' } } },
}, config);

// ─── INDICADOR 32 ────────────────────────────────────────────────────────
function plotInd32Stack() {
  const dom = PAYLOAD.series.filter(r => r.serie === 'cabotagem:cabotagem_domestica')
                            .sort((a,b)=>a.data.localeCompare(b.data));
  const off = PAYLOAD.series.filter(r => r.serie === 'cabotagem:offshore')
                            .sort((a,b)=>a.data.localeCompare(b.data));
  Plotly.react('ind32-stack', [
    { x: dom.map(r => r.data+'-01'), y: dom.map(r => r.sum12_mt),
      name:'Cabotagem doméstica', stackgroup:'one', mode:'lines',
      line:{ color: CORES.cabotagem_domestica, width:0 }, fillcolor: CORES.cabotagem_domestica },
    { x: off.map(r => r.data+'-01'), y: off.map(r => r.sum12_mt),
      name:'Petróleo offshore (FPSO/ZEE)', stackgroup:'one', mode:'lines',
      line:{ color: CORES.offshore, width:0 }, fillcolor: CORES.offshore },
  ], {
    ...layoutBase,
    yaxis: { ...layoutBase.yaxis, title:{ text:'Milhões de toneladas (12 meses)', font:{ color:'#9ca3af' } } },
    legend: { orientation:'h', y:-0.2, x:0, font:{ color:'#d1d5db' } },
  }, config);
}
plotInd32Stack();

function plotInd32Rotas(top) {
  const rotas = PAYLOAD.rotas.slice(0, top).reverse();
  const cores = rotas.map(r => r.cagr_pct > 15 ? '#00A652'
                              : r.cagr_pct > 0 ? '#0099D8' : '#c1322f');
  Plotly.react('ind32-rotas', [{
    x: rotas.map(r => r.teu_acumulado / 1e6),
    y: rotas.map(r => '#' + r.rank + ' ' + r.origem.slice(0,16) + ' (' + r.uf_origem + ') → ' + r.destino.slice(0,16) + ' (' + r.uf_destino + ')'),
    type:'bar', orientation:'h',
    marker:{ color: cores },
    text: rotas.map(r => ' ' + (r.cagr_pct != null ? (r.cagr_pct>=0?'+':'') + r.cagr_pct.toFixed(1) + '%/ano' : '')),
    textposition:'outside',
    textfont:{ color:'#d1d5db', size: 10 },
    hovertemplate:'<b>%{y}</b><br>%{x:,.2f} milhões de TEUs acumulados<br>Crescimento médio anual: %{text}<extra></extra>',
  }], {
    ...layoutBase,
    margin: { l: 230, r: 70, t: 10, b: 40 },
    xaxis: { ...layoutBase.xaxis, title:{ text:'Milhões de TEUs (acumulado desde 2010)', font:{ color:'#9ca3af' } } },
    yaxis: { ...layoutBase.yaxis, automargin:true, tickfont:{ color:'#d1d5db', size:10 } },
    showlegend:false,
    height: Math.max(340, rotas.length * 26),
  }, config);
}
plotInd32Rotas(10);
document.getElementById('ind32-rotas-top').addEventListener('change', e => plotInd32Rotas(+e.target.value));

// ─── INDICADOR 33 — REFEITO ──────────────────────────────────────────────
function plotInd33(natKey) {
  const dados = PAYLOAD.portos.naturezas[natKey];
  if (!dados) return;

  const natCagr = dados.cagr_natureza_pct;
  const labelNat = dados.natureza_label.toLowerCase();

  // Headline narrativa
  document.getElementById('ind33-headline').innerHTML =
    '<strong>' + dados.natureza_label + '</strong> no Brasil cresceu ' +
    '<strong style="color:#D4922A">' + (natCagr >= 0 ? '+' : '') + natCagr.toFixed(1) + '% ao ano</strong> ' +
    'entre ' + dados.periodo + '. Veja como cada porto se comparou a essa média:';

  const gan = dados.ganhadores.slice(0, 8);
  const per = dados.perdedores.slice(0, 8).reverse();
  const all = [...per, ...gan];

  // Eixo X = CAGR do porto (não mais divergência)
  const tr = {
    x: all.map(p => p.cagr_pct),
    y: all.map(p => p.porto.slice(0,28) + ' (' + p.uf + ')'),
    type: 'bar', orientation:'h',
    marker:{ color: all.map(p => p.cagr_pct >= natCagr ? '#00A652' : '#c1322f') },
    text: all.map(p => '  ' + (p.cagr_pct>=0?'+':'') + p.cagr_pct.toFixed(1) + '%/ano · ' +
                        p.volume_mt.toFixed(1) + ' Mt'),
    textposition:'outside',
    textfont:{ color:'#d1d5db', size: 10 },
    hovertemplate:
      '<b>%{y}</b><br>' +
      'Crescimento do porto: %{x:+.1f}% ao ano<br>' +
      'Média do setor (' + labelNat + '): ' + (natCagr>=0?'+':'') + natCagr.toFixed(1) + '% ao ano<br>' +
      '%{customdata}<extra></extra>',
    customdata: all.map(p => p.cagr_pct >= natCagr ? '→ ganhou espaço no mercado' : '→ perdeu espaço no mercado'),
  };

  Plotly.react('ind33-plot', [tr], {
    ...layoutBase,
    margin: { l: 230, r: 130, t: 10, b: 50 },
    xaxis: { ...layoutBase.xaxis, title:{ text:'Crescimento médio anual do porto (%)', font:{ color:'#9ca3af' } },
              zeroline:true, zerolinecolor:'#9ca3af', zerolinewidth:1 },
    yaxis: { ...layoutBase.yaxis, automargin:true, tickfont:{ color:'#d1d5db', size:10 } },
    shapes: [{
      type:'line',
      x0: natCagr, x1: natCagr, y0: -0.5, y1: all.length - 0.5,
      line:{ color:'#D4922A', width:2, dash:'dash' },
    }],
    annotations: [{
      x: natCagr, y: all.length - 0.3, xref:'x', yref:'y',
      text: 'Média nacional: ' + (natCagr>=0?'+':'') + natCagr.toFixed(1) + '%',
      showarrow:false,
      font:{ color:'#D4922A', size:11 },
      bgcolor:'#2c2c2c',
      bordercolor:'#D4922A',
      borderwidth:1,
      borderpad:4,
      yanchor:'bottom',
    }],
    showlegend:false,
    height: Math.max(500, all.length * 34),
  }, config);
}
plotInd33('granel_solido');
document.getElementById('ind33-natureza').addEventListener('change', e => plotInd33(e.target.value));

// ─── HELPERS ──────────────────────────────────────────────────────────────
function fmt(n, d) {
  d = d == null ? 1 : d;
  return n == null ? '—' : new Intl.NumberFormat('pt-BR', { minimumFractionDigits:d, maximumFractionDigits:d }).format(n);
}
</script>
</body>
</html>
"""

payload = json.dumps(embed, ensure_ascii=False, separators=(",", ":"))
html = TEMPLATE.replace("__PAYLOAD__", payload)
OUT.write_text(html, encoding="utf-8")
print(f"OK: {OUT}")
print(f"Tamanho: {OUT.stat().st_size/1024:,.1f} KB")
