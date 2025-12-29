# app.py
import datetime as dt              # 날짜 계산용
import pandas as pd               # 데이터프레임
import streamlit as st            # 웹 UI
import yfinance as yf             # 야후 폴백용 시세
from dateutil.relativedelta import relativedelta  # 개월 단위 기간 계산
import altair as alt              # 라인 차트 렌더

# 페이지 메타와 타이틀
st.set_page_config(layout="wide", page_title="차트")
st.title("차트")

# ---------------- 옵션 ----------------
with st.sidebar:
    st.subheader("옵션")
    # 기간 선택. pykrx와 yfinance 모두 일봉 기준
    period = st.selectbox("조회 기간",
                          ["5d","1mo","3mo","6mo","1y","2y","5y","max"], index=2)
    # 자동 새로고침 토글. 데이터 소스별 캐시는 유지됨
    autorefresh = st.toggle("30초 자동 새로고침", value=False)
    # 워치리스트 초기화
    if st.button("기본 4개로 리셋"):
        st.session_state.watch = ["133690.KS","132030.KS","308620.KS","261240.KS"]
    # streamlit의 데이터 캐시 무효화
    if st.button("캐시 비우기"):
        st.cache_data.clear()

# 자동 새로고침 트리거
if autorefresh:
    st.experimental_autorefresh(interval=30_000, key="auto")

# ---------------- 기본 워치리스트 ----------------
# 최초 로드 시 기본값 주입. 이후에는 세션 상태 유지
DEFAULT = ["133690.KS", "132030.KS", "308620.KS", "261240.KS"]
if "watch" not in st.session_state:
    st.session_state.watch = DEFAULT

# ---------------- 검색/추가 ----------------
# 좌: 검색어, 우: 티커 직접 추가
col_a, col_b = st.columns([2, 1])
with col_a:
    q = st.text_input("종목 검색", placeholder="ETF 이름 또는 코드 일부")
with col_b:
    add_raw = st.text_input("티커 추가", placeholder="쉼표로 여러 개 입력")

def _append_tickers(raw: str):
    """쉼표로 분리된 입력을 워치리스트에 중복 없이 추가"""
    items = [x.strip() for x in raw.split(",") if x.strip()]
    for t in items:
        if t not in st.session_state.watch:
            st.session_state.watch.append(t)

# 직접 입력 즉시 반영
if add_raw:
    _append_tickers(add_raw)

def search_krx(query: str) -> pd.DataFrame:
    """
    KRX ETF 코드/이름 검색.
    - pykrx의 전체 ETF 코드 리스트를 조회 후 부분일치 필터
    - 반환: Ticker(.KS), Name
    """
    if not query.strip():
        return pd.DataFrame()
    try:
        from pykrx import stock
        etfs = stock.get_etf_ticker_list()
        rows = [(f"{code}.KS", stock.get_etf_ticker_name(code)) for code in etfs]
        df = pd.DataFrame(rows, columns=["Ticker","Name"])
        m = df["Ticker"].str.contains(query, case=False) | df["Name"].str.contains(query, case=False)
        return df[m].head(50)
    except Exception:
        # 네트워크/모듈 에러 시 빈 결과
        return pd.DataFrame()

# 검색 결과 렌더 + 각 행의 추가 버튼
if q:
    res = search_krx(q)
    if not res.empty:
        st.markdown("#### 검색 결과")
        for _, r in res.iterrows():
            c1, c2, c3 = st.columns([3,6,1])
            c1.code(r["Ticker"])          # .KS 형태의 야후 호환 티커
            c2.write(r["Name"])           # 한글명
            if c3.button("추가", key=f"add_{r['Ticker']}"):
                _append_tickers(r["Ticker"])

# ---------------- 이름/데이터 로드 ----------------
# 기간 프리셋 → 개월 수 매핑. pykrx 날짜 계산에 사용
PERIOD_MONTHS = {"5d":0,"1mo":1,"3mo":3,"6mo":6,"1y":12,"2y":24,"5y":60}

@st.cache_data(ttl=3600, show_spinner=False)
def get_korean_name(ticker: str) -> str:
    """
    ETF 한글명 조회.
    - 우선 pykrx의 종목명
    - 실패 시 yfinance의 shortName
    """
    code = ticker.split(".")[0]
    try:
        from pykrx import stock
        return stock.get_etf_ticker_name(code) or ticker
    except Exception:
        pass
    try:
        return yf.Ticker(ticker).info.get("shortName", ticker)
    except Exception:
        return ticker

@st.cache_data(ttl=180, show_spinner=False)
def load_series(ticker: str, period: str) -> pd.Series:
    """
    시계열 종가 Series 반환.
    - 1순위: pykrx get_etf_ohlcv_by_date(일봉)
      · 날짜 형식: YYYYMMDD
      · 인덱스 → DatetimeIndex 변환
    - 2순위: yfinance.download(period, 1d, auto_adjust)
    - 반환: float64 Series, 이름은 ticker
    """
    # pykrx 시도
    try:
        from pykrx import stock
        code = ticker.split(".")[0]
        if period == "max":
            start = "19900101"
        elif period == "5d":
            # 주말 포함 여유 10일
            start = (dt.date.today() - dt.timedelta(days=10)).strftime("%Y%m%d")
        else:
            start = (dt.date.today() - relativedelta(months=PERIOD_MONTHS.get(period,3))).strftime("%Y%m%d")
        end = dt.date.today().strftime("%Y%m%d")
        df = stock.get_etf_ohlcv_by_date(start, end, code)
        if df is not None and not df.empty and "종가" in df.columns:
            s = pd.to_numeric(df["종가"], errors="coerce").dropna()
            s.index = pd.to_datetime(s.index)  # Altair에 필요한 datetime 인덱스
            s.name = ticker
            return s.astype("float64")
    except Exception:
        # pykrx 실패는 조용히 폴백
        pass

    # yfinance 폴백
    df = yf.download(ticker, period=period, interval="1d",
                     progress=False, auto_adjust=True, threads=False)
    if df.empty or "Close" not in df:
        return pd.Series(dtype="float64")
    s = df["Close"].dropna()
    s.name = ticker
    return s.astype("float64")

def render_series(s: pd.Series):
    """
    Altair 라인 차트 렌더.
    - 0 기준선 고정 해제(zero=False)
    - 툴팁: 날짜, 종가(콤마, 소수2)
    """
    df = s.rename("Close").to_frame().reset_index()
    df.columns = ["Date","Close"]
    ch = (
        alt.Chart(df)
        .mark_line()
        .encode(
            x=alt.X("Date:T", title=""),
            y=alt.Y("Close:Q", title="", scale=alt.Scale(zero=False)),
            tooltip=[alt.Tooltip("Date:T"), alt.Tooltip("Close:Q", format=",.2f")],
        ).properties(height=260)
    )
    st.altair_chart(ch, use_container_width=True)

# ---------------- 렌더 ----------------
valid, diag = [], []
for idx, t in enumerate(st.session_state.watch):
    # 개별 시계열 로드
    s = load_series(t, period)
    if s.empty:
        st.warning(f"{t}: 데이터 없음")
        continue
    valid.append((idx, t, s))
    # 진단용 요약(선택 표시)
    diag.append({
        "티커": t,
        "데이터수": len(s),
        "시작일": s.index.min(),
        "최근일": s.index.max(),
        "최근종가": float(s.iloc[-1])
    })

st.subheader("📈 차트")

# 워치리스트 관리 버튼
tools = st.columns([1,1,6])
with tools[0]:
    if st.button("전체 제거"):
        st.session_state.watch = []
with tools[1]:
    if st.button("중복 제거"):
        # 순서 유지하며 중복 제거
        st.session_state.watch = list(dict.fromkeys(st.session_state.watch))

# 유효 시리즈가 없으면 안내
if not valid:
    st.info("표시할 ETF가 없습니다. 기본 4개로 리셋하거나 추가하세요.")
else:
    # 2열 그리드로 차트 배치
    cols = st.columns(2)
    for i, (idx, t, s) in enumerate(valid):
        with cols[i % 2]:
            # --- 제목: 한글명 + 코드(회색 작은 글씨) ---
            name = get_korean_name(t)
            st.markdown(
                f"### {name} "
                f"<span style='color:#7f8c8d;font-size:0.9rem'>`{t}`</span>",
                unsafe_allow_html=True
            )

            # --- 가격 요약: 종가, 전일대비, 변화율 ---
            last = float(s.iloc[-1])
            prev = float(s.iloc[-2]) if len(s) > 1 else None
            delta = (last - prev) if prev else 0.0
            delta_pct = (delta / prev * 100) if prev else 0.0
            c1, c2, c3 = st.columns(3)
            c1.metric("종가", f"{last:,.0f}원")
            c2.metric("전일대비", f"{delta:+,.0f}", f"{delta_pct:+.2f}%")
            c3.metric("데이터수", len(s))

            # --- 라인 차트 ---
            render_series(s)

            # --- 개별 제거 버튼 ---
            # 키는 인덱스+티커 조합으로 고유화
            if st.button("× 제거", key=f"rm_{idx}_{t}"):
                st.session_state.watch.remove(t)
                st.experimental_rerun()

# ---------------- 진단 ----------------
# 내부 상태 점검용 테이블. 기본 비표시
show_diag = st.checkbox("진단 보기", value=False)
if show_diag and diag:
    st.dataframe(pd.DataFrame(diag), use_container_width=True, hide_index=True)

# 법적 고지
st.caption("KRX 및 야후 데이터. 지연 가능. 투자 판단 참고용.")
