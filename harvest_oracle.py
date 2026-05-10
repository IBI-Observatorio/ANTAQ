"""
Harvest Oracle — Previsão de congestionamento portuário com 90 dias de antecedência.

Pipeline:
  1. Carrega estimativas mensais de safra da CONAB (LevantamentoGraos.txt)
  2. Constrói a matriz de roteamento porto × mês a partir do histórico ANTAQ
  3. Calcula pressão esperada sobre cada porto para os próximos meses
  4. Treina LightGBM (quantile) com features de rolling T1 e target log1p
  5. Calibra quantis com conformal prediction (split conformal)
  6. Gera previsão probabilística calibrada (p10/p25/p50/p75/p90) por porto

Uso rápido:
    from harvest_oracle import HarvestOracle
    oracle = HarvestOracle()
    oracle.fit()
    oracle.relatorio(meses=3)
    df = oracle.prever(meses=3)
"""

from pathlib import Path
import warnings
import numpy as np
import pandas as pd
import lightgbm as lgb
import antaq

warnings.filterwarnings("ignore")

# ── Constantes ─────────────────────────────────────────────────────────────────

CONAB_DIR = Path("dados/conab")

PRODUTO_NCM = {
    "SOJA":            ["1201"],
    "MILHO":           ["1005"],
    "TRIGO":           ["1001"],
    "ARROZ":           ["1006"],
    "SORGO GRANIFERO": ["1007"],
}

INICIO_ANO_AGRICOLA = {
    "SOJA":            10,
    "MILHO":           10,
    "TRIGO":            7,
    "ARROZ":           10,
    "SORGO GRANIFERO": 10,
}

MES_PT = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4,
    "mai": 5, "jun": 6, "jul": 7, "ago": 8,
    "set": 9, "out": 10, "nov": 11, "dez": 12,
}
MES_PT_INV = {v: k for k, v in MES_PT.items()}

# Features v3 — crescimento_rota captura migração estrutural de rotas (Arco Norte)
FEATURES = [
    "pressao",           # vol_esperado / capacidade_historica
    "delta_est",         # variação % da estimativa vs levantamento anterior
    "mes_alvo",          # mês calendário previsto (1-12)
    "lag_meses",         # horizonte de previsão (1, 2 ou 3)
    "levantamento",      # número do levantamento CONAB (1-12)
    "tendencia_ano",     # ano - 2010 (tendência secular)
    "crescimento_rota",  # slope relativo do share de mercado (últimos 3 anos) ← novo
    "t1_lag1",           # T1 no mês de publicação do levantamento
    "t1_rolling_3m",     # média T1 nos 3 meses anteriores à publicação
    "t1_std_3m",         # desvio-padrão T1 nos 3 meses anteriores
    "t1_hist_mes",       # mediana histórica de T1 para este porto×mês_alvo
    "vol_est_kt",
    "cap_media_kt",
]

QUANTIS = [0.10, 0.25, 0.50, 0.75, 0.90]
MIN_AMOSTRAS_TREINO = 25
MIN_AMOSTRAS_CALIB  = 8
CALIB_SPLIT_RATIO   = 0.25   # últimos 25% do tempo → calibração


# ── Carregamento ────────────────────────────────────────────────────────────────

def _carregar_levantamento() -> pd.DataFrame:
    path = CONAB_DIR / "LevantamentoGraos.txt"
    df = pd.read_csv(path, sep=";", encoding="latin-1", dtype=str, on_bad_lines="skip")
    df.columns = df.columns.str.strip()
    for col in df.select_dtypes("object").columns:
        df[col] = df[col].str.strip()

    df = df[df["produto"].isin(PRODUTO_NCM)].copy()
    df["producao_mil_t"] = pd.to_numeric(
        df["producao_mil_t"].str.replace(",", "."), errors="coerce"
    )
    df["id_levantamento"] = pd.to_numeric(df["id_levantamento"], errors="coerce")
    df = df.dropna(subset=["producao_mil_t", "id_levantamento"])
    df = df[df["id_levantamento"].between(1, 12)]

    tot = (
        df.groupby(["ano_agricola", "produto", "id_levantamento"])["producao_mil_t"]
        .sum()
        .reset_index()
        .rename(columns={"id_levantamento": "levantamento"})
    )

    rows = []
    for _, r in tot.iterrows():
        ano_str = r["ano_agricola"]
        lev = int(r["levantamento"])
        produto = r["produto"]
        inicio_mes = INICIO_ANO_AGRICOLA.get(produto, 10)
        try:
            ano_inicio = int(str(ano_str).split("/")[0])
        except ValueError:
            continue
        mes_pub  = ((inicio_mes - 1 + (lev - 1)) % 12) + 1
        ano_pub  = ano_inicio + ((inicio_mes - 1 + (lev - 1)) // 12)
        rows.append({
            "produto":            produto,
            "ano_agricola":       ano_str,
            "levantamento":       lev,
            "ano_pub":            ano_pub,
            "mes_pub":            mes_pub,
            "producao_brasil_kt": r["producao_mil_t"],
        })

    result = pd.DataFrame(rows)
    result["data_pub"] = pd.to_datetime(
        result["ano_pub"].astype(str) + "-"
        + result["mes_pub"].astype(str).str.zfill(2) + "-01"
    )
    return result.sort_values(["produto", "data_pub"]).reset_index(drop=True)


def _carregar_historico_portos() -> pd.DataFrame:
    db = antaq.conectar()
    ncms_str = ", ".join(
        f"'{n}'" for ncms in PRODUTO_NCM.values() for n in ncms
    )
    df = db.sql(f"""
        SELECT
            a."Porto Atracação"  AS porto,
            a.Ano                AS ano,
            a.Mes                AS mes_pt,
            c.CDMercadoria       AS ncm,
            SUM(c."VLPesoCargaBruta") / 1000.0 AS volume_kt
        FROM Carga c
        JOIN Atracacao a USING (IDAtracacao)
        WHERE c.CDMercadoria IN ({ncms_str})
        AND c.Sentido = 'Embarcados'
        AND c."FlagLongoCurso" = 1
        GROUP BY 1, 2, 3, 4
    """).df()
    db.close()
    df["mes"] = df["mes_pt"].map(MES_PT)
    df = df.dropna(subset=["mes"])
    df["mes"] = df["mes"].astype(int)
    ncm_to_produto = {n: p for p, ns in PRODUTO_NCM.items() for n in ns}
    df["produto"] = df["ncm"].map(ncm_to_produto)
    return df.dropna(subset=["produto"])


def _carregar_t1_historico() -> pd.DataFrame:
    db = antaq.conectar()
    df = db.sql("""
        SELECT
            a."Porto Atracação"  AS porto,
            a.Ano                AS ano,
            a.Mes                AS mes_pt,
            AVG(TRY_CAST(replace(t.TEsperaAtracacao, ',', '.') AS DOUBLE)) AS t1_medio_h,
            STDDEV(TRY_CAST(replace(t.TEsperaAtracacao, ',', '.') AS DOUBLE)) AS t1_std_h,
            COUNT(*) AS n
        FROM TemposAtracacao t
        JOIN Atracacao a USING (IDAtracacao)
        WHERE a."Tipo de Operação" = 'Movimentação da Carga'
        GROUP BY 1, 2, 3
        HAVING COUNT(*) >= 5
    """).df()
    db.close()
    df["mes"] = df["mes_pt"].map(MES_PT)
    df = df.dropna(subset=["mes"])
    df["mes"] = df["mes"].astype(int)
    return df


# ── Matriz de roteamento ────────────────────────────────────────────────────────

def _construir_matriz_roteamento(hist: pd.DataFrame) -> pd.DataFrame:
    total_br = (
        hist.groupby(["produto", "ano", "mes"])["volume_kt"]
        .sum().reset_index()
        .rename(columns={"volume_kt": "total_br_kt"})
    )
    h = hist.merge(total_br, on=["produto", "ano", "mes"])
    h["fraction"] = h["volume_kt"] / h["total_br_kt"].replace(0, np.nan)
    h = h.dropna(subset=["fraction"])
    return (
        h.groupby(["produto", "mes", "porto"])["fraction"]
        .mean().reset_index()
        .rename(columns={"fraction": "frac_media"})
    )


# ── Rolling T1 ─────────────────────────────────────────────────────────────────

def _construir_t1_lookup(t1: pd.DataFrame) -> pd.DataFrame:
    """Tabela indexada por (porto, ano, mes) para lookup rápido de T1."""
    return t1.set_index(["porto", "ano", "mes"])[["t1_medio_h", "t1_std_h"]].copy()


def _rolling_t1(lookup: pd.DataFrame, porto: str, ano: int, mes: int, window: int = 3):
    """Calcula média e std de T1 nos `window` meses anteriores a (ano, mes)."""
    vals = []
    for i in range(1, window + 1):
        m_total = mes - i
        m_ano = ano + (m_total - 1) // 12 if m_total < 1 else ano
        m_mes = ((m_total - 1) % 12) + 1 if m_total < 1 else m_total
        try:
            v = lookup.loc[(porto, m_ano, m_mes), "t1_medio_h"]
            if not np.isnan(v):
                vals.append(float(v))
        except KeyError:
            pass
    return (np.mean(vals) if vals else np.nan,
            np.std(vals)  if len(vals) > 1 else np.nan)


def _t1_hist_mes(t1: pd.DataFrame, porto: str, mes: int) -> float:
    """Mediana histórica de T1 para um porto × mês específico."""
    sub = t1[(t1["porto"] == porto) & (t1["mes"] == mes)]["t1_medio_h"]
    return float(sub.median()) if len(sub) > 0 else np.nan


def _construir_crescimento_rota(hist: pd.DataFrame) -> pd.Series:
    """
    Para cada (porto, produto, ano_ref), slope relativo do share de mercado
    calculado com regressão linear nos últimos 3 anos até ano_ref.

    crescimento_rota > 0 → porto ganhando share (ex: Arco Norte)
    crescimento_rota < 0 → porto perdendo share (ex: Rio Grande em soja)

    Retorna pd.Series indexada por (porto, produto, ano_ref).
    """
    total_br = (
        hist.groupby(["produto", "ano"])["volume_kt"].sum()
        .reset_index().rename(columns={"volume_kt": "total_br_kt"})
    )
    porto_ano = hist.groupby(["produto", "ano", "porto"])["volume_kt"].sum().reset_index()
    h = porto_ano.merge(total_br, on=["produto", "ano"])
    h["share"] = h["volume_kt"] / h["total_br_kt"].replace(0, np.nan)
    h = h.dropna(subset=["share"])

    rows = []
    for (porto, produto), g in h.groupby(["porto", "produto"]):
        g = g.sort_values("ano")
        for ano in g["ano"].values:
            window = g[g["ano"] <= ano].tail(3)
            if len(window) < 2:
                continue
            x = window["ano"].values.astype(float)
            y = window["share"].values
            x_c = x - x.mean()
            denom = float(np.dot(x_c, x_c))
            slope = float(np.dot(x_c, y) / denom) if denom > 0 else 0.0
            mean_share = float(y.mean())
            crescimento = slope / mean_share if mean_share > 1e-9 else 0.0
            rows.append({
                "porto": porto,
                "produto": produto,
                "ano_ref": int(ano),
                "crescimento_rota": crescimento,
            })

    return (
        pd.DataFrame(rows)
        .set_index(["porto", "produto", "ano_ref"])["crescimento_rota"]
        .sort_index()
    )


# ── Feature engineering ─────────────────────────────────────────────────────────

def _construir_features(
    levantamento: pd.DataFrame,
    hist_portos:  pd.DataFrame,
    matriz:       pd.DataFrame,
    t1:           pd.DataFrame,
    crescimento:  pd.Series,
) -> pd.DataFrame:
    lookup = _construir_t1_lookup(t1)

    # Capacidade histórica média por porto × produto × mês
    cap = (
        hist_portos.groupby(["produto", "mes", "porto"])["volume_kt"]
        .mean().reset_index()
        .rename(columns={"volume_kt": "cap_media_kt"})
    )

    # Mediana histórica de T1 por porto × mês (sazonalidade)
    t1_hist_mes_df = (
        t1.groupby(["porto", "mes"])["t1_medio_h"]
        .median().reset_index()
        .rename(columns={"t1_medio_h": "t1_hist_mes"})
    )

    # Delta estimativa por produto × data_pub
    lev_sorted = levantamento.sort_values(["produto", "data_pub"]).copy()
    lev_sorted["prod_lag1"] = lev_sorted.groupby("produto")["producao_brasil_kt"].shift(1)
    lev_sorted["delta_est"] = (
        (lev_sorted["producao_brasil_kt"] - lev_sorted["prod_lag1"])
        / lev_sorted["prod_lag1"].replace(0, np.nan)
    )
    delta_map = lev_sorted.set_index(["produto", "data_pub"])["delta_est"].to_dict()

    rows = []
    for _, lev in levantamento.iterrows():
        produto  = lev["produto"]
        ano_pub  = lev["ano_pub"]
        mes_pub  = lev["mes_pub"]
        prod_kt  = lev["producao_brasil_kt"]
        delta    = delta_map.get((produto, lev["data_pub"]), np.nan)

        for lag in range(1, 4):
            mes_alvo = ((mes_pub - 1 + lag) % 12) + 1
            ano_alvo = ano_pub + ((mes_pub - 1 + lag) // 12)

            fracs = matriz[(matriz["produto"] == produto) & (matriz["mes"] == mes_alvo)]
            cap_p = cap[(cap["produto"] == produto) & (cap["mes"] == mes_alvo)]

            for _, fr in fracs.iterrows():
                porto   = fr["porto"]
                vol_est = prod_kt * fr["frac_media"]

                cap_row = cap_p[cap_p["porto"] == porto]["cap_media_kt"]
                cap_val = float(cap_row.iloc[0]) if len(cap_row) > 0 else np.nan
                pressao = vol_est / cap_val if cap_val and cap_val > 0 else np.nan

                # T1 no mês de publicação
                try:
                    t1_lag1 = float(lookup.loc[(porto, ano_pub, mes_pub), "t1_medio_h"])
                except KeyError:
                    t1_lag1 = np.nan

                # Rolling T1 (3 meses antes da publicação)
                t1_roll, t1_std_roll = _rolling_t1(lookup, porto, ano_pub, mes_pub, window=3)

                # Mediana histórica para este porto × mês_alvo
                t1_hm = _t1_hist_mes(t1, porto, mes_alvo)

                # Crescimento de rota: usar ano_pub como referência (sem lookahead)
                try:
                    cres = float(crescimento.loc[(porto, produto, ano_pub)])
                except KeyError:
                    try:
                        sub = crescimento.loc[(porto, produto)]
                        cres = float(sub.iloc[-1])
                    except (KeyError, AttributeError):
                        cres = np.nan

                rows.append({
                    "porto":           porto,
                    "produto":         produto,
                    "ano_pub":         ano_pub,
                    "mes_pub":         mes_pub,
                    "data_pub":        lev["data_pub"],
                    "levantamento":    lev["levantamento"],
                    "lag_meses":       lag,
                    "ano_alvo":        ano_alvo,
                    "mes_alvo":        mes_alvo,
                    "vol_est_kt":      vol_est,
                    "cap_media_kt":    cap_val,
                    "pressao":         pressao,
                    "prod_total_kt":   prod_kt,
                    "delta_est":       delta,
                    "crescimento_rota": cres,
                    "t1_lag1":         t1_lag1,
                    "t1_rolling_3m":   t1_roll,
                    "t1_std_3m":       t1_std_roll,
                    "t1_hist_mes":     t1_hm,
                    "tendencia_ano":   ano_alvo - 2010,
                })

    feat = pd.DataFrame(rows)

    # Join com T1 observado no mês alvo (target)
    t1_target = (
        t1.rename(columns={"ano": "ano_alvo", "mes": "mes_alvo",
                            "t1_medio_h": "t1_target", "n": "n_at_target"})
        [["porto", "ano_alvo", "mes_alvo", "t1_target", "n_at_target"]]
    )
    feat = feat.merge(t1_target, on=["porto", "ano_alvo", "mes_alvo"], how="left")

    # Mediana global por porto como fallback para features ausentes
    mediana_porto = (
        feat.groupby("porto")[["crescimento_rota", "t1_lag1", "t1_rolling_3m", "t1_std_3m", "t1_hist_mes"]]
        .median()
    )
    for col in ["crescimento_rota", "t1_lag1", "t1_rolling_3m", "t1_std_3m", "t1_hist_mes"]:
        mask = feat[col].isna()
        if mask.any():
            feat.loc[mask, col] = feat.loc[mask, "porto"].map(mediana_porto[col])

    feat = feat.dropna(subset=["pressao", "t1_target"])
    feat = feat[feat["t1_target"] >= 0]
    return feat


# ── Modelo ──────────────────────────────────────────────────────────────────────

def _treinar_modelos(feat: pd.DataFrame) -> dict:
    """
    Treina LightGBM quantílico com target log1p(T1).
    Retorna dict: porto → {quantil → (modelo, shift_calibracao)}
    """
    feat = feat.copy()
    feat["log_t1"] = np.log1p(feat["t1_target"])

    # Preencher NaN com mediana global das features
    med_global = feat[FEATURES].median()
    X_all = feat[FEATURES].fillna(med_global)
    y_log = feat["log_t1"]

    params_base = dict(
        objective="quantile",
        n_estimators=500,
        learning_rate=0.04,
        num_leaves=31,
        min_child_samples=8,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_lambda=0.5,
        verbose=-1,
    )

    modelos = {}

    for porto in feat["porto"].unique():
        mask_porto = feat["porto"] == porto
        n_porto = mask_porto.sum()
        if n_porto < MIN_AMOSTRAS_TREINO:
            continue

        # Split temporal: últimos CALIB_SPLIT_RATIO para calibração
        idx_porto = np.where(mask_porto)[0]
        n_calib = max(MIN_AMOSTRAS_CALIB, int(n_porto * CALIB_SPLIT_RATIO))
        idx_treino = idx_porto[:-n_calib]
        idx_calib  = idx_porto[-n_calib:]

        if len(idx_treino) < MIN_AMOSTRAS_TREINO:
            # Poucos dados: treinar em tudo, sem calibração
            idx_treino = idx_porto
            idx_calib  = idx_porto[-n_calib:]

        X_tr = X_all.iloc[idx_treino]
        y_tr = y_log.iloc[idx_treino]
        X_ca = X_all.iloc[idx_calib]
        y_ca = feat["t1_target"].iloc[idx_calib].values

        modelos[porto] = {}

        for q in QUANTIS:
            m = lgb.LGBMRegressor(**{**params_base, "alpha": q})
            m.fit(X_tr, y_tr)

            # Calibração conformal: ajusta shift para atingir cobertura nominal
            pred_ca_log = m.predict(X_ca)
            pred_ca = np.expm1(pred_ca_log)

            if q == 0.50:
                # Para mediana: ajusta bias (shift aditivo na escala original)
                erros = y_ca - pred_ca
                shift = float(np.median(erros))
            else:
                # Para quantis extremos: ajusta cobertura empírica
                # q < 0.5 → lower bound; queremos que fraction(y < pred) ≈ q
                empirical_coverage = float(np.mean(y_ca <= pred_ca))
                target_cov = q
                # Escala multiplicativa simples para corrigir sub/sobrecobertura
                if empirical_coverage > 0:
                    scale = target_cov / empirical_coverage
                    # shift na escala log para escalar previsão
                    shift = float(np.log(max(scale, 0.01)))
                else:
                    shift = 0.0

            modelos[porto][q] = (m, shift)

    return modelos


def _prever_porto(modelos_porto: dict, X_pred: pd.DataFrame) -> dict:
    """Aplica modelos de um porto e retorna previsões calibradas."""
    preds = {}
    for q, (m, shift) in modelos_porto.items():
        val_log = float(m.predict(X_pred)[0])
        if q == 0.50:
            preds[q] = max(0.0, np.expm1(val_log) + shift)
        else:
            preds[q] = max(0.0, np.expm1(val_log + shift))
    return preds


# ── Classe principal ────────────────────────────────────────────────────────────

class HarvestOracle:
    """
    Previsão probabilística calibrada de congestionamento (T1) nos portos de granel.

    Exemplo:
        oracle = HarvestOracle()
        oracle.fit()
        oracle.relatorio(meses=3)
    """

    def __init__(self):
        self.levantamento_:  pd.DataFrame | None = None
        self.hist_portos_:   pd.DataFrame | None = None
        self.matriz_:        pd.DataFrame | None = None
        self.t1_hist_:       pd.DataFrame | None = None
        self.feat_:          pd.DataFrame | None = None
        self.modelos_:       dict | None = None
        self._lookup:        pd.DataFrame | None = None
        self._crescimento_:  pd.Series | None = None
        self._fitted = False

    def fit(self, verbose: bool = True) -> "HarvestOracle":
        if verbose:
            print("[ 1/5 ] Carregando estimativas CONAB...")
        self.levantamento_ = _carregar_levantamento()
        if verbose:
            print(f"        {len(self.levantamento_):,} estimativas  "
                  f"({self.levantamento_['produto'].nunique()} produtos, "
                  f"{self.levantamento_['ano_pub'].min()}–{self.levantamento_['ano_pub'].max()})")

        if verbose:
            print("[ 2/5 ] Carregando histórico de exportações ANTAQ...")
        self.hist_portos_ = _carregar_historico_portos()
        if verbose:
            print(f"        {len(self.hist_portos_):,} registros porto×mês×produto  "
                  f"({self.hist_portos_['porto'].nunique()} portos)")

        if verbose:
            print("[ 3/5 ] Construindo matriz de roteamento porto × mês...")
        self.matriz_ = _construir_matriz_roteamento(self.hist_portos_)
        if verbose:
            print(f"        {len(self.matriz_):,} entradas na matriz")

        if verbose:
            print("[ 4/5 ] Carregando T1 histórico e montando features...")
        self.t1_hist_      = _carregar_t1_historico()
        self._lookup       = _construir_t1_lookup(self.t1_hist_)
        self._crescimento_ = _construir_crescimento_rota(self.hist_portos_)
        self.feat_         = _construir_features(
            self.levantamento_, self.hist_portos_, self.matriz_,
            self.t1_hist_, self._crescimento_,
        )
        if verbose:
            print(f"        {len(self.feat_):,} amostras  "
                  f"(portos={self.feat_['porto'].nunique()}, "
                  f"{self.feat_['ano_alvo'].min()}–{self.feat_['ano_alvo'].max()})")

        if verbose:
            print("[ 5/5 ] Treinando LightGBM quantílico com calibração conformal...")
        self.modelos_ = _treinar_modelos(self.feat_)
        if verbose:
            print(f"        Modelos prontos: {len(self.modelos_)} portos × {len(QUANTIS)} quantis")

        self._fitted = True
        return self

    # ── prever ───────────────────────────────────────────────────────────────

    def prever(
        self,
        meses: int = 3,
        data_referencia: str | None = None,
    ) -> pd.DataFrame:
        """
        Gera previsão probabilística calibrada de T1 para os próximos `meses` meses.

        Args:
            meses: horizonte (1–3)
            data_referencia: 'YYYY-MM' do mês de referência (default: último levantamento)
        """
        assert self._fitted, "Chame .fit() antes de .prever()"

        data_ref = (
            pd.Timestamp(data_referencia + "-01")
            if data_referencia
            else self.levantamento_["data_pub"].max()
        )

        ultimos = (
            self.levantamento_[self.levantamento_["data_pub"] <= data_ref]
            .sort_values("data_pub")
            .groupby("produto").last()
            .reset_index()
        )

        med_global = self.feat_[FEATURES].median()

        rows = []
        for _, lev in ultimos.iterrows():
            produto = lev["produto"]
            lev_hist = (
                self.levantamento_[
                    (self.levantamento_["produto"] == produto)
                    & (self.levantamento_["data_pub"] <= data_ref)
                ].sort_values("data_pub").tail(2)
            )
            delta = (
                (lev_hist.iloc[-1]["producao_brasil_kt"] - lev_hist.iloc[-2]["producao_brasil_kt"])
                / lev_hist.iloc[-2]["producao_brasil_kt"]
                if len(lev_hist) == 2 else 0.0
            )

            for lag in range(1, meses + 1):
                mes_alvo = ((lev["mes_pub"] - 1 + lag) % 12) + 1
                ano_alvo = lev["ano_pub"] + ((lev["mes_pub"] - 1 + lag) // 12)

                fracs  = self.matriz_[
                    (self.matriz_["produto"] == produto) & (self.matriz_["mes"] == mes_alvo)
                ]
                cap_p = (
                    self.hist_portos_[
                        (self.hist_portos_["produto"] == produto)
                        & (self.hist_portos_["mes"] == mes_alvo)
                    ].groupby("porto")["volume_kt"].mean()
                )

                for _, fr in fracs.iterrows():
                    porto = fr["porto"]
                    if porto not in self.modelos_:
                        continue

                    vol_est = lev["producao_brasil_kt"] * fr["frac_media"]
                    cap_val = float(cap_p.get(porto, np.nan))
                    pressao = vol_est / cap_val if cap_val > 0 else np.nan

                    # Features de rolling T1
                    try:
                        t1_lag1 = float(self._lookup.loc[(porto, lev["ano_pub"], lev["mes_pub"]), "t1_medio_h"])
                    except KeyError:
                        t1_lag1 = np.nan
                    t1_roll, t1_std = _rolling_t1(
                        self._lookup, porto, lev["ano_pub"], lev["mes_pub"], window=3
                    )
                    t1_hm = _t1_hist_mes(self.t1_hist_, porto, mes_alvo)

                    # Crescimento de rota para este porto×produto
                    try:
                        cres = float(self._crescimento_.loc[(porto, produto, lev["ano_pub"])])
                    except KeyError:
                        try:
                            sub = self._crescimento_.loc[(porto, produto)]
                            cres = float(sub.iloc[-1]) if hasattr(sub, "iloc") else float(sub)
                        except (KeyError, TypeError):
                            cres = np.nan

                    # Fallback com mediana global
                    row_feat = {
                        "pressao":         pressao if not np.isnan(pressao) else float(med_global["pressao"]),
                        "delta_est":       delta,
                        "mes_alvo":        mes_alvo,
                        "lag_meses":       lag,
                        "levantamento":    int(lev["levantamento"]),
                        "tendencia_ano":   ano_alvo - 2010,
                        "crescimento_rota": cres   if not np.isnan(cres)    else float(med_global["crescimento_rota"]),
                        "t1_lag1":         t1_lag1 if not np.isnan(t1_lag1) else float(med_global["t1_lag1"]),
                        "t1_rolling_3m":   t1_roll if not np.isnan(t1_roll) else float(med_global["t1_rolling_3m"]),
                        "t1_std_3m":       t1_std  if not np.isnan(t1_std)  else float(med_global["t1_std_3m"]),
                        "t1_hist_mes":     t1_hm   if not np.isnan(t1_hm)   else float(med_global["t1_hist_mes"]),
                        "vol_est_kt":      vol_est,
                        "cap_media_kt":    cap_val if not np.isnan(cap_val) else 0.0,
                    }
                    X_pred = pd.DataFrame([row_feat])
                    preds = _prever_porto(self.modelos_[porto], X_pred)

                    t1_hist_mediana = float(
                        self.feat_[self.feat_["porto"] == porto]["t1_target"].median()
                    )
                    alerta = (
                        "CRITICO"  if preds[0.50] > t1_hist_mediana * 1.5 else
                        "ELEVADO"  if preds[0.50] > t1_hist_mediana * 1.2 else
                        "MODERADO" if preds[0.50] > t1_hist_mediana       else
                        "NORMAL"
                    )
                    rows.append({
                        "porto":               porto,
                        "produto":             produto,
                        "mes_alvo":            MES_PT_INV.get(mes_alvo, str(mes_alvo)),
                        "ano_alvo":            ano_alvo,
                        "lag_meses":           lag,
                        "vol_est_kt":          round(vol_est, 1),
                        "pressao":             round(pressao, 2) if not np.isnan(pressao) else None,
                        "crescimento_rota_pct": round(cres * 100, 1) if not np.isnan(cres) else None,
                        "t1_p10":              round(preds[0.10], 1),
                        "t1_p25":              round(preds[0.25], 1),
                        "t1_p50":              round(preds[0.50], 1),
                        "t1_p75":              round(preds[0.75], 1),
                        "t1_p90":              round(preds[0.90], 1),
                        "t1_historico":        round(t1_hist_mediana, 1),
                        "alerta":              alerta,
                    })

        return (
            pd.DataFrame(rows)
            .sort_values(["lag_meses", "t1_p50"], ascending=[True, False])
            .reset_index(drop=True)
        )

    # ── relatorio ─────────────────────────────────────────────────────────────

    def relatorio(self, meses: int = 3, min_vol_kt: float = 1000.0) -> None:
        """
        Imprime relatório de previsão.

        Args:
            meses:      horizonte de previsão
            min_vol_kt: filtra portos com volume esperado < min_vol_kt (mil ton)
        """
        prev = self.prever(meses=meses)
        prev = prev[prev["vol_est_kt"] >= min_vol_kt]
        data_ref = self.levantamento_["data_pub"].max()

        ICONE = {"CRITICO": "🔴", "ELEVADO": "🟠", "MODERADO": "🟡", "NORMAL": "🟢"}

        print(f"\n{'='*80}")
        print(f"  HARVEST ORACLE v3 — Previsao Calibrada de Congestionamento Portuario")
        print(f"  Referencia : {data_ref.strftime('%b/%Y')}  |  Ultimo levantamento CONAB")
        print(f"  Horizonte  : {meses} {'mes' if meses == 1 else 'meses'}  |  "
              f"Filtro: vol >= {min_vol_kt:,.0f} mil ton")
        print(f"{'='*80}")

        latest = (
            self.levantamento_[self.levantamento_["data_pub"] == data_ref]
            [["produto", "levantamento", "producao_brasil_kt"]]
        )
        print("\n  Estimativas CONAB (referencia):")
        for _, r in latest.iterrows():
            print(f"    {r['produto']:<25} {r['levantamento']:>2}o lev.  "
                  f"{r['producao_brasil_kt']:>10,.0f} mil ton")

        for lag in sorted(prev["lag_meses"].unique()):
            bloco = prev[prev["lag_meses"] == lag]
            if bloco.empty:
                continue
            mes_ref = bloco["mes_alvo"].iloc[0]
            ano_ref = bloco["ano_alvo"].iloc[0]
            print(f"\n  --- {mes_ref.upper()}/{ano_ref}  (t+{lag}) ---")
            print(f"  {'Porto':<42} {'Prod':<6} {'Vol(kt)':>8} "
                  f"{'p25':>6} {'p50':>6} {'p75':>6} {'Hist':>6} {'Rota':>6}  Status")
            print(f"  {'-'*103}")

            criticos  = bloco[bloco["alerta"] == "CRITICO"]
            elevados  = bloco[bloco["alerta"] == "ELEVADO"]
            outros    = bloco[~bloco["alerta"].isin(["CRITICO", "ELEVADO"])]

            for sub in [criticos, elevados, outros]:
                for _, r in sub.iterrows():
                    icone = ICONE[r["alerta"]]
                    cres_pct = r.get("crescimento_rota_pct", float("nan"))
                    cres_str = (
                        f"{cres_pct:+.0f}%"
                        if not (isinstance(cres_pct, float) and np.isnan(cres_pct))
                        else "  n/a"
                    )
                    print(f"  {r['porto']:<42} {r['produto']:<6} "
                          f"{r['vol_est_kt']:>8,.0f} "
                          f"{r['t1_p25']:>6.0f} {r['t1_p50']:>6.0f} {r['t1_p75']:>6.0f} "
                          f"{r['t1_historico']:>6.0f} {cres_str:>6}  {icone} {r['alerta']}")

        print(f"\n{'='*80}")
        print("  p25/p50/p75 = T1 previsto (horas) nos percentis 25/50/75")
        print("  Hist = mediana historica de T1 no porto  |  Vol = volume estimado (mil ton)")
        print("  Rota = crescimento anual do share de mercado (% a.a.)  +ganhou share  -perdeu share")
        print(f"{'='*80}\n")

    # ── matriz_roteamento ─────────────────────────────────────────────────────

    def matriz_roteamento(self, produto: str = "SOJA") -> pd.DataFrame:
        assert self._fitted
        m = self.matriz_[self.matriz_["produto"] == produto].copy()
        m["frac_pct"] = (m["frac_media"] * 100).round(1)
        pivot = m.pivot_table(
            index="porto", columns="mes", values="frac_pct", fill_value=0
        )
        pivot.columns = [MES_PT_INV.get(c, str(c)) for c in pivot.columns]
        return pivot.loc[pivot.max(axis=1) > 0.5].sort_values("jun", ascending=False)

    # ── importancia de features ────────────────────────────────────────────────

    def importancia_features(self, top_n: int = 12) -> pd.DataFrame:
        """
        Importância média das features nos modelos de mediana (q=0.50) de todos os portos.
        """
        assert self._fitted
        all_imp = []
        for porto, qs in self.modelos_.items():
            if 0.50 not in qs:
                continue
            m, _ = qs[0.50]
            imp = pd.Series(m.feature_importances_, index=FEATURES)
            all_imp.append(imp)
        if not all_imp:
            return pd.DataFrame()
        mean_imp = pd.concat(all_imp, axis=1).mean(axis=1).sort_values(ascending=False)
        return mean_imp.head(top_n).reset_index().rename(columns={"index": "feature", 0: "importancia"})

    # ── validacao walk-forward ─────────────────────────────────────────────────

    def validar(self, anos_teste: list[int] | None = None) -> pd.DataFrame:
        """
        Validação walk-forward: treina nos anos anteriores, avalia no ano de teste.
        Reporta MAE e cobertura empírica do intervalo p25–p75.
        """
        assert self._fitted
        if anos_teste is None:
            anos_teste = [2022, 2023, 2024]

        feat = self.feat_.copy()
        feat["log_t1"] = np.log1p(feat["t1_target"])
        med_global = feat[FEATURES].median()

        resultados = []
        for ano_teste in anos_teste:
            treino = feat[feat["ano_alvo"] < ano_teste]
            teste  = feat[feat["ano_alvo"] == ano_teste]
            if treino.empty or teste.empty:
                continue

            mod_temp = _treinar_modelos(treino)

            X_test = teste[FEATURES].fillna(med_global)
            y_test = teste["t1_target"].values

            for porto in mod_temp:
                mask = teste["porto"].values == porto
                if mask.sum() < 3:
                    continue
                Xt = X_test[mask]
                yt = y_test[mask]

                preds = _prever_porto(mod_temp[porto], Xt)

                mae    = float(np.mean(np.abs(preds[0.50] - yt)))
                cob_50 = float(np.mean((yt >= preds[0.25]) & (yt <= preds[0.75])))
                cob_80 = float(np.mean((yt >= preds[0.10]) & (yt <= preds[0.90])))

                resultados.append({
                    "ano_teste":           ano_teste,
                    "porto":               porto,
                    "n":                   int(mask.sum()),
                    "MAE_h":               round(mae, 1),
                    "cobertura_50pct":     round(cob_50 * 100, 1),  # target: 50%
                    "cobertura_80pct":     round(cob_80 * 100, 1),  # target: 80%
                })

        return pd.DataFrame(resultados).sort_values(["ano_teste", "MAE_h"])


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    oracle = HarvestOracle()
    oracle.fit()

    print("\n=== IMPORTANCIA DE FEATURES ===")
    print(oracle.importancia_features().to_string(index=False))

    print("\n=== PREVISAO (proximos 3 meses, vol >= 2000 mil ton) ===")
    oracle.relatorio(meses=3, min_vol_kt=2000)

    print("\n=== VALIDACAO WALK-FORWARD ===")
    val = oracle.validar()
    # Resumo por ano
    resumo = (
        val.groupby("ano_teste")
        .agg(
            n_portos=("porto", "count"),
            MAE_medio=("MAE_h", "mean"),
            MAE_mediano=("MAE_h", "median"),
            cobertura_50pct=("cobertura_50pct", "mean"),
            cobertura_80pct=("cobertura_80pct", "mean"),
        )
        .round(1)
    )
    print("\n  Resumo por ano:")
    print(resumo.to_string())
    print("\n  Detalhe por porto (2024):")
    print(val[val["ano_teste"] == 2024].to_string(index=False))
