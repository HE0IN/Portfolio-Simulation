# pip install streamlit streamlit-aggrid pandas openpyxl
import streamlit as st
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode

st.set_page_config(layout="wide", page_title="피벗/소계(Community)")

# --- 0) 예시 데이터(엑셀로 대체 가능) ---
# raw = pd.read_excel("data.xlsx", sheet_name=0)
raw = pd.DataFrame({
    "프로젝트": ["A","A","A","B","B","C"],
    "공정": ["절단","용접","도장","절단","용접","도장"],
    "월": ["2025-09","2025-09","2025-10","2025-10","2025-10","2025-11"],
    "수량": [10,20,5,7,13,9],
    "금액": [100,220,40,70,160,90]
})

st.sidebar.header("피벗 옵션")
idx_cols  = st.sidebar.multiselect("행 인덱스", ["프로젝트","공정"], default=["프로젝트","공정"])
col_col   = st.sidebar.selectbox("열 피벗", ["(없음)","월"], index=1)
val_col   = st.sidebar.selectbox("값", ["수량","금액"], index=0)
agg       = st.sidebar.selectbox("집계", ["sum","mean","max","min","count"], index=0)

# --- 1) 피벗 생성(판다스) ---
pivot = pd.pivot_table(
    raw,
    index=idx_cols,
    columns=None if col_col=="(없음)" else [col_col],
    values=val_col,
    aggfunc=agg,
    fill_value=0
)
# MultiIndex 컬럼 평탄화
if isinstance(pivot.columns, pd.MultiIndex):
    pivot.columns = ["_".join([str(x) for x in t if x!='']) for t in pivot.columns.to_flat_index()]
else:
    pivot.columns = [str(c) for c in pivot.columns]
pivot = pivot.reset_index()

# --- 2) 소계 행 삽입(상위 그룹 기준) ---
def insert_subtotals(df: pd.DataFrame, group_keys: list[str], value_cols: list[str]):
    if not group_keys:
        return df
    out = []
    for gvals, gdf in df.groupby(group_keys, sort=False):
        out.append(gdf)
        sub = {k: (f"{gvals if isinstance(gvals, str) else gvals[0]} 소계" if i==0 else "") for i,k in enumerate(group_keys)}
        for c in value_cols:
            sub[c] = gdf[c].sum(numeric_only=True) if pd.api.types.is_numeric_dtype(gdf[c]) else None
        out.append(pd.DataFrame([sub]))
    return pd.concat(out, ignore_index=True)
def mark_group_first(df: pd.DataFrame, group_key: str) -> pd.DataFrame:
    df = df.copy()
    first_flags = []
    prev = object()
    for v in df[group_key].astype(str).fillna(""):
        is_sub = v.endswith("소계")
        val_for_cmp = v if not is_sub else object()  # 소계는 새 덩어리로 간주
        first = (val_for_cmp != prev) and (not is_sub) and (v != "")
        first_flags.append(first)
        prev = val_for_cmp
    df["_groupFirst"] = first_flags
    return df
value_cols = [c for c in pivot.columns if c not in idx_cols]
with_sub = insert_subtotals(pivot, group_keys=[idx_cols[0]] if idx_cols else [], value_cols=value_cols)
with_sub = mark_group_first(with_sub, idx_cols[0] if idx_cols else with_sub.columns[0])

# --- 3) 병합 유사: 연속 구간에서 첫 행만 값, 나머지는 빈칸(보기용) ---
def collapse_repeats(df: pd.DataFrame, cols: list[str]):
    df = df.copy()
    for c in cols:
        prev = None
        for i in range(len(df)):
            cur = df.at[i, c] if c in df.columns else None
            if pd.notna(cur) and isinstance(cur, str) and cur.endswith("소계"):
                prev = None
                continue
            if cur == prev:
                df.at[i, c] = ""
            else:
                prev = cur
    return df

vis = collapse_repeats(with_sub, idx_cols)

# --- 4) 스타일(JS): 소계 행 강조, 그룹 첫 행 상단 보더 ---
row_style = JsCode("""
function(params) {
  const d = params.data || {};
  const isSub = Object.values(d).some(v => String(v || '').includes('소계'));
  if (isSub) return { backgroundColor: '#fffde7', fontWeight: 600 };
  if (d._groupFirst) return { borderTop: '2px solid #e0e0e0' };
  return null;
}
""")

g = GridOptionsBuilder.from_dataframe(vis)
g.configure_grid_options(getRowStyle=row_style)
g.configure_default_column(resizable=True, sortable=True, filter=True)
g.configure_column("_groupFirst", hide=True)  # 보이지 않게
# 숫자 포맷
for c in value_cols:
    g.configure_column(c, type=["numericColumn"], valueFormatter=JsCode("x => x.value == null ? '' : Number(x.value).toLocaleString()"))

# 총계(하단 고정)
total_row = {k:"" for k in vis.columns}
total_row[idx_cols[0] if idx_cols else vis.columns[0]] = "총계"
for c in value_cols:
    total_row[c] = with_sub[c].fillna(0).sum()
grid_options = g.build()

st.subheader("피벗 + 소계 + 총계(Community)")
AgGrid(
    vis,
    gridOptions=grid_options,
    update_mode=GridUpdateMode.NO_UPDATE,
    theme="alpine",
    height=560,
    fit_columns_on_grid_load=True,
    pinned_bottom_row_data=[total_row],
    allow_unsafe_jscode=True
)

st.caption("팁: 피벗 축을 바꾸면 즉시 재계산. 소계는 상위 그룹(첫 인덱스) 기준.")
