# pages/02_💼_포트폴리오.py
import numpy as np
import pandas as pd
import yfinance as yf
import streamlit as st
from dateutil.relativedelta import relativedelta
from datetime import date

st.set_page_config(layout="wide")
st.title("💼 포트폴리오")

st.markdown("현재 보유와 목표 비중을 입력하고, 단순 월적립 가정으로 미래 추정.")

# 왼쪽: 현재 보유 입력
lc, rc = st.columns([1,1])

with lc:
    st.subheader("현재 보유")
    st.caption("직접 입력하거나 가격 자동가져오기 체크")
    auto_price = st.checkbox("가격 자동가져오기(yfinance)", value=True)
    holdings_df = st.data_editor(
        pd.DataFrame(
            [
                {"티커":"VOO","수량":10.0,"평단가":400.0},
                {"티커":"TLT","수량":50.0,"평단가":90.0},
                {"티커":"IAU","수량":100.0,"평단가":40.0},
            ]
        ),
        num_rows="dynamic",
        use_container_width=True,
        key="holdings_editor"
    )

with rc:
    st.subheader("목표 비중")
    target_df = st.data_editor(
        pd.DataFrame(
            [
                {"자산":"미국주식(VOO)","티커":"VOO","비중(%)":50.0,"기대수익률(연,%)":7.0},
                {"자산":"장기채(TLT)","티커":"TLT","비중(%)":30.0,"기대수익률(연,%)":3.0},
                {"자산":"금(IAU)","티커":"IAU","비중(%)":20.0,"기대수익률(연,%)":2.0},
            ]
        ),
        num_rows="dynamic",
        use_container_width=True,
        key="target_editor"
    )

# 현금흐름·기간
st.subheader("적립/기간 가정")
cc1, cc2, cc3, cc4 = st.columns([1,1,1,1])
with cc1:
    start_nav = st.number_input("초기 현금(₩, 보유 외 현금)", 0, 10_000_000_000, 0, step=100_000)
with cc2:
    monthly_contrib = st.number_input("월 적립(₩)", 0, 10_000_000_000, 500_000, step=100_000)
with cc3:
    years = st.number_input("기간(년)", 1, 50, 5)
with cc4:
    rebalance = st.selectbox("리밸런싱", ["적립금만 비중 맞추기","매월 정밀 리밸런스"], index=0)

base_ccy = "KRW"
fx_krw_per_usd = st.number_input("환율 가정 KRW/USD", 500, 5000, 1400)

# 가격 가져오기
def last_price(ticker: str):
    try:
        if auto_price:
            tk = yf.Ticker(ticker)
            fi = getattr(tk, "fast_info", None)
            p = fi.get("last_price", None) if fi else None
            if p is None:
                h = yf.download(ticker, period="1d", interval="1m", progress=False)
                if not h.empty:
                    p = float(h["Close"].dropna().iloc[-1])
            return float(p) if p is not None else None
        else:
            return None
    except Exception:
        return None

# 보유 평가
def evaluate_holdings(df: pd.DataFrame):
    vals = []
    for _, r in df.iterrows():
        t = str(r["티커"]).strip()
        q = float(r.get("수량",0) or 0)
        avg = float(r.get("평단가",0) or 0)
        px = last_price(t)
        if px is None:
            px = avg if avg>0 else 0.0
        # 달러 자산 가정: KRW 환산 필요. 간단히 모두 USD로 가정.
        mv_krw = q * px * fx_krw_per_usd
        vals.append({"티커":t,"수량":q,"가격(USD)":px,"평단가(USD)":avg,"평가액(KRW)":mv_krw})
    out = pd.DataFrame(vals)
    return out, out["평가액(KRW)"].sum()

hold_eval, total_mv = evaluate_holdings(holdings_df)
st.subheader("현재 평가")
st.dataframe(hold_eval, use_container_width=True, hide_index=True)
st.metric("현재 총 평가액(KRW)", f"{int(total_mv):,}")

# 목표 비중 표준화
tgt = target_df.copy()
tgt["비중"] = tgt["비중(%)"].astype(float) / 100.0
weight_sum = tgt["비중"].sum()
if weight_sum <= 0:
    st.stop()
tgt["비중"] = tgt["비중"] / weight_sum
tgt["월수익률"] = ((1.0 + tgt["기대수익률(연,%)"].astype(float)/100.0) ** (1/12.0)) - 1.0

# 현재 비중 계산
cur_weights = {}
if total_mv > 0:
    for _, r in hold_eval.iterrows():
        cur_weights[r["티커"]] = cur_weights.get(r["티커"],0.0) + r["평가액(KRW)"]/total_mv

# 리밸런싱 제안(금액 기준)
plan_rows = []
for _, r in tgt.iterrows():
    tkr = r["티커"]
    tw = float(r["비중"])
    cw = float(cur_weights.get(tkr,0.0))
    delta_w = tw - cw
    # 제안 금액 = 목표-현재 * 총평가
    plan_amt = int(delta_w * total_mv)
    plan_rows.append({"티커":tkr,"현재비중":round(cw*100,2),"목표비중":round(tw*100,2),"제안금액(KRW)":plan_amt})
st.subheader("리밸런싱 제안")
st.dataframe(pd.DataFrame(plan_rows), use_container_width=True, hide_index=True)

# 단순 미래 추정: 월 적립 + 기대수익률, 월별
months = int(years * 12)
timeline = pd.date_range(date.today(), periods=months+1, freq="MS")
nav = []
alloc_amt = {r["티커"]: 0.0 for _, r in tgt.iterrows()}  # KRW 기준

# 초기: 보유 평가액 + 현금
nav0 = total_mv + start_nav
nav.append(nav0)

def rebalance_step(alloc_amt: dict, target_weights: dict, total_amt: float):
    # 총액을 목표 비중으로 재분배
    for k in target_weights:
        alloc_amt[k] = total_amt * target_weights[k]
    return alloc_amt

tgt_w = {r["티커"]: float(r["비중"]) for _, r in tgt.iterrows()}
tgt_mu_m = {r["티커"]: float(r["월수익률"]) for _, r in tgt.iterrows()}

# 초기 분해: 현재 보유는 티커 매핑되지 않은 금액은 현금으로 간주
for k in list(alloc_amt.keys()):
    # 현재 보유 중 동일 티커는 해당 금액만큼 시작
    amt = float(hold_eval.loc[hold_eval["티커"]==k, "평가액(KRW)"].sum())
    alloc_amt[k] = amt

other_amt = nav0 - sum(alloc_amt.values())
if other_amt < 0:
    other_amt = 0.0

for i in range(1, months+1):
    # 1) 수익 반영
    for k in alloc_amt:
        alloc_amt[k] *= (1.0 + tgt_mu_m[k])
    # 2) 적립금 투입
    invest_pool = monthly_contrib + other_amt
    other_amt = 0.0
    if rebalance == "매월 정밀 리밸런스":
        # 총액 재산정 후 목표비중으로 재분배
        total_now = sum(alloc_amt.values()) + invest_pool
        alloc_amt = rebalance_step(alloc_amt, tgt_w, total_now)
    else:
        # 적립금만 목표 비중으로 배분
        for k in alloc_amt:
            alloc_amt[k] += invest_pool * tgt_w[k]
    # 3) NAV 기록
    nav.append(sum(alloc_amt.values()))

nav_series = pd.Series(nav, index=timeline)
st.subheader("미래 추정 NAV")
st.line_chart(nav_series.rename("KRW"), height=280)

# 요약
total_contrib = monthly_contrib * months + start_nav
gain = nav_series.iloc[-1] - (total_mv + total_contrib)
c1, c2, c3 = st.columns(3)
c1.metric("기말 추정 자산(KRW)", f"{int(nav_series.iloc[-1]):,}")
c2.metric("총 납입액(KRW)", f"{int(total_contrib):,}")
c3.metric("추정 평가이익(KRW)", f"{int(gain):,}")

st.caption("단순 결정론 모델. 세금/수수료/실시간 체결 고려 없음. 환율은 고정 가정.")
