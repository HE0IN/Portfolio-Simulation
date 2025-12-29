# pages/01_🏆_종목검색.py
import datetime as dt
import pandas as pd
import streamlit as st
from pykrx import stock

st.set_page_config(layout="wide", page_title="종목 순위")
st.title("🏆 종목 검색")

# ---------- 옵션 ----------
scope = st.selectbox("범위", ["KOSPI", "KOSDAQ", "KOSPI+KOSDAQ", "ETF"], index=0)
metric = st.selectbox("지표", ["거래대금", "거래량", "등락률"], index=0)
topn = st.slider("개수", 5, 100, 20, step=5)
reload_btn = st.button("새로고침")

# ---------- 유틸 ----------
def _bizday(when=None) -> str:
    """오늘이 휴장일이면 가장 가까운 영업일로 보정"""
    d = (when or dt.date.today()).strftime("%Y%m%d")
    return stock.get_nearest_business_day_in_a_week(d)

@st.cache_data(ttl=300, show_spinner=False)
def load_equity_ohlcv(date:str, market:str) -> pd.DataFrame:
    """주식 OHLCV + 종목명"""
    df = stock.get_market_ohlcv_by_ticker(date, market=market)
    df = df.rename_axis("종목코드").reset_index()
    df["종목명"] = df["종목코드"].map(stock.get_market_ticker_name)
    df["시장"] = market
    return df

@st.cache_data(ttl=300, show_spinner=False)
def load_etf_ohlcv(date:str) -> pd.DataFrame:
    """ETF OHLCV + 종목명"""
    df = stock.get_etf_ohlcv_by_ticker(date)
    df = df.rename_axis("종목코드").reset_index()
    df["종목명"] = df["종목코드"].map(stock.get_etf_ticker_name)
    df["시장"] = "ETF"
    # pykrx ETF에는 등락률 컬럼이 없을 수 있음 → 종가/시가로 근사
    if "등락률" not in df.columns and {"시가","종가"}.issubset(df.columns):
        df["등락률"] = (df["종가"] / df["시가"] - 1.0) * 100
    return df

def load_scope(date:str, scope:str) -> pd.DataFrame:
    if scope == "KOSPI":
        return load_equity_ohlcv(date, "KOSPI")
    if scope == "KOSDAQ":
        return load_equity_ohlcv(date, "KOSDAQ")
    if scope == "KOSPI+KOSDAQ":
        return pd.concat([
            load_equity_ohlcv(date, "KOSPI"),
            load_equity_ohlcv(date, "KOSDAQ"),
        ], ignore_index=True)
    return load_etf_ohlcv(date)

# ---------- 로드 ----------
try:
    if reload_btn:
        st.cache_data.clear()
    d = _bizday()
    df = load_scope(d, scope)
except Exception as e:
    st.error(f"데이터 로드 실패: {e}")
    st.stop()

# ---------- 정렬 ----------
valid_cols = [c for c in ["거래대금","거래량","등락률"] if c in df.columns]
if metric not in valid_cols:
    st.warning(f"선택한 지표 '{metric}'는 {scope}에 없음. 사용 가능: {', '.join(valid_cols)}")
    metric = valid_cols[0]

# NaN 제거 후 정렬
base = df.dropna(subset=[metric]).copy()
ascending = True if metric == "등락률" and base[metric].max() <= 0 else False
# 등락률은 보통 상위 상승률을 보므로 내림차순. 전종목 음수면 상승 없음 → 내림차순 유지해도 무방.
ranked = base.sort_values(metric, ascending=False).head(topn)

# ---------- 출력 ----------
cols_show = ["종목코드","종목명","시장","거래대금","거래량","등락률","시가","고가","저가","종가"]
cols_show = [c for c in cols_show if c in ranked.columns]
st.caption(f"{d} 기준 · {scope} · 지표: {metric} · 상위 {len(ranked)}")
st.dataframe(
    ranked[cols_show],
    use_container_width=True,
    hide_index=True,
)

st.caption("원천: KRX · pykrx. 일중 수치는 변동 가능. 검색량 지표는 외부 트렌드 데이터 연동이 필요함.")
