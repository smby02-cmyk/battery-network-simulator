"""한누리 배터리 공급망 시뮬레이터 (Streamlit).

실행: streamlit run app.py
"""
import pandas as pd
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st

from sim import Model, Options, config as C

st.set_page_config(page_title="배터리 공급망 시뮬레이터", page_icon="🔋", layout="wide")

NAME = C.PLANT_NAME
SC = C.SCENARIOS
NAVY, BLUE, SKY, GRAY, LGRAY = C.NAVY, C.BLUE, C.SKY, C.GRAY, "#C9D3E3"


# ------------------------------------------------------------------ 캐시
@st.cache_resource
def model():
    return Model()


@st.cache_data(show_spinner=False)
def npv_cached(plants: tuple, scen: str, decarb: tuple = (), decarb_from: int = 2030, delay: int = 0):
    o = Options(scen=scen, decarb=dict(decarb), decarb_from=decarb_from, delay=delay)
    return model().npv(list(plants), o)


@st.cache_data(show_spinner=False)
def cashflows_cached(plants: tuple, scen: str, decarb: tuple = (), decarb_from: int = 2030):
    o = Options(scen=scen, decarb=dict(decarb), decarb_from=decarb_from)
    return model().cashflows(list(plants), o)


@st.cache_data(show_spinner=False)
def allocate_cached(plants: tuple, year: int, scen: str, decarb: tuple = (), decarb_from: int = 2030):
    o = Options(scen=scen, decarb=dict(decarb), decarb_from=decarb_from)
    alloc, shadow, obj, dem = model().allocate(list(plants), year, o)
    return alloc, shadow, obj, dem


def inc(add: tuple, scen: str, decarb: tuple = (), decarb_from: int = 2030, delay: int = 0):
    base = npv_cached(tuple(C.EXISTING), scen)
    return npv_cached(tuple(C.EXISTING) + add, scen, decarb, decarb_from, delay) - base


M = model()
DN = M.D.oem_site.to_dict()


def region(d):
    return "유럽" if d.startswith("D_EU") else ("아시아" if d.startswith("D_AS") else "중동·남미")


def fmt_m(v):  # 백만 달러 → 억 달러 문자열
    return f"{v/100:+,.1f}억$"


# ------------------------------------------------------------------ 사이드바
st.sidebar.title("🔋 시뮬레이션 설정")
scen = st.sidebar.selectbox("시나리오", list(SC), format_func=lambda s: SC[s], index=0)
year = st.sidebar.slider("기준 연도 (지도·배정)", 2026, 2045, 2035)
st.sidebar.markdown("**네트워크 구성**")
st.sidebar.caption("기존: 오창 (한국) 35GWh + 브로츠와프 (폴란드) 86→90GWh")
cands = st.sidebar.multiselect("신규 후보지 추가", C.CANDIDATES, default=["F_EU_HU_DEBRECEN"], format_func=lambda p: NAME[p])
dec = st.sidebar.slider("브로츠와프 탈탄소화 (직접 연결 저탄소 전력 비중)", 0, 50, 0, step=1, format="%d%%") / 100
dec_from = st.sidebar.selectbox("저탄소 전력 확보 연도", [2030, 2032, 2035], index=0)
plants = tuple(C.EXISTING + cands)
decarb = ((C.WROCLAW, dec),) if dec > 0 else ()
st.sidebar.divider()
st.sidebar.caption("ver1 = 규제 미시행 (시장기반, PPA·GO 인정)\n\nver2 = 규제 시행 (위치기반 + 탄소발자국 상한 2030년 65kg, 2035년 60kg)")
st.sidebar.caption("자료: INU GLR Case Study 「탄소 국경 위의 배터리 공장」, battery_supply_chain(SIMPLE).xlsx (가상 데이터)")

st.title("한누리에너지솔루션 유럽 배터리 공급망 시뮬레이터")
st.caption("2026–2045년 · 비용·탄소·리드타임·20년 재무·시나리오 리스크를 한 화면에서 · WACC 9%, 2026년 시점 할인")

tabs = st.tabs(["① 권고안 요약", "② 네트워크 지도", "③ 도착원가 (Q1)", "④ 배정·생산능력 (Q2)",
                "⑤ 탄소 규제 (Q3)", "⑥ 투자 평가 (Q4)", "⑦ 시나리오·실물옵션 (Q5)", "⑧ 검증"])

# ------------------------------------------------------------------ ① 권고안 요약
with tabs[0]:
    st.subheader("규제가 오든 안 오든 유럽 시장을 지키는 네트워크")
    st.markdown("**권고:** 데브레첸 (헝가리) 단계적 신설 + 브로츠와프 (폴란드) 탈탄소화 준비 · 브로츠와프 증설 기각")
    with st.spinner("20년 NPV 계산 중 (첫 실행 시 수십 초)…"):
        v1 = inc(tuple(cands), "base", decarb, dec_from)
        v2 = inc(tuple(cands), "cap", decarb, dec_from)
        a1, _, _, _ = allocate_cached(plants, 2035, "base", decarb, dec_from)
        a2, _, _, _ = allocate_cached(plants, 2035, "cap", decarb, dec_from)
    eu1 = a1[a1.demand.str.startswith("D_EU")].gwh.sum(); eu2 = a2[a2.demand.str.startswith("D_EU")].gwh.sum()
    eu_cap = 0.7 * M.demand(2035, Options())[[d for d in M.D.index if d.startswith("D_EU")]].sum()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("현재 구성 증분 NPV · ver1", fmt_m(v1), help="기존 네트워크 대비 20년 증분 NPV (규제 미시행)")
    c2.metric("현재 구성 증분 NPV · ver2", fmt_m(v2), help="기존 네트워크 대비 20년 증분 NPV (규제 시행). 탈탄소화 비용은 미포함")
    c3.metric("2035 유럽 공급 · ver1", f"{eu1:.1f} GWh", f"공략 가능 {eu_cap:.1f} 중 {eu1/eu_cap*100:.0f}%", delta_color="off")
    c4.metric("2035 유럽 공급 · ver2", f"{eu2:.1f} GWh", f"공략 가능 {eu_cap:.1f} 중 {eu2/eu_cap*100:.0f}%", delta_color="off")
    st.caption("현재 구성 = 사이드바에서 선택한 신규 후보지·탈탄소화. 탈탄소화 투자비는 케이스에 없어 NPV에서 빼지 않았다(⑦에서 손익분기로 판단).")
    st.markdown("""
| 권고 | 내용 | 근거 |
| --- | --- | --- |
| (i) 유럽 생산거점 | 데브레첸 (헝가리) 40GWh **단계적 확정** (지금 입찰 대응 준비 → 2027년 초 본투자 결정) · 브로츠와프 증설 **기각** · 두 번째 공장 **보류** | 두 버전 모두 증분 NPV 양(+), 기대값 1위·최대후회 최소 |
| (ii) 공장 역할 | 오창 = 마더 팩토리 + 아시아·중동 + 유럽 부족분 스윙 / 브로츠와프 = 유럽 주력 + 탈탄소화 | 고탄소 시 오창 kWh당 +9.7달러, ver2에서 오창·브로츠와프 유럽 퇴출 |
| (iii) 고객별 공급 | 유럽 12곳 70% 공급 유지 (ver2는 탈탄소화 성공 시) | ④ 탭 고객별 배정 |
| (iv) 탄소 헤지 | 브로츠와프 직접 연결 저탄소 전력 35%, 저탄소 소재, 데브레첸 저탄소 거점 | ⑤·⑦ 탭 |
| (v) 전환 조건 | 위임법 위치기반 확정 → 탈탄소화 착수 / 2027년 초 수주·수요 → 데브레첸 본투자 | ⑦ 탭 |
""")

# ------------------------------------------------------------------ ② 지도
with tabs[1]:
    st.subheader(f"{year}년 네트워크와 물동량 · {SC[scen]}")
    alloc, shadow, obj, dem = allocate_cached(plants, year, scen, decarb, dec_from)
    F = M.F.reset_index(); D = M.D.reset_index()
    D["dem"] = D.demand_id.map(dem)
    vol = alloc.groupby("plant").gwh.sum()
    F["state"] = F.factory_id.map(lambda p: "기존" if p in C.EXISTING else ("선택" if p in cands else "미선택"))
    F["color"] = F.state.map({"기존": [31, 56, 100, 230], "선택": [47, 107, 216, 230], "미선택": [180, 188, 200, 140]})
    F["label"] = F.factory_id.map(NAME)
    F["gwh"] = F.factory_id.map(lambda p: round(float(vol.get(p, 0)), 1))
    arcs = alloc.merge(F[["factory_id", "latitude", "longitude"]], left_on="plant", right_on="factory_id") \
        .merge(D[["demand_id", "latitude", "longitude"]], left_on="demand", right_on="demand_id", suffixes=("_f", "_d"))
    arcs["w"] = arcs.gwh.clip(lower=0.5) / 3
    arcs["label"] = arcs.plant.map(NAME) + " → " + arcs.demand.map(DN) + " " + arcs.gwh.round(1).astype(str) + "GWh"
    layers = [
        pdk.Layer("ArcLayer", arcs, get_source_position=["longitude_f", "latitude_f"], get_target_position=["longitude_d", "latitude_d"],
                  get_width="w", great_circle=True, get_source_color=[47, 107, 216, 160], get_target_color=[112, 150, 219, 160], pickable=True),
        pdk.Layer("ScatterplotLayer", D, get_position=["longitude", "latitude"], get_radius="dem * 4000",
                  get_fill_color=[138, 148, 166, 120], pickable=True),
        pdk.Layer("ScatterplotLayer", F, get_position=["longitude", "latitude"], get_radius=60000,
                  get_fill_color="color", stroked=True, get_line_color=[255, 255, 255], line_width_min_pixels=1, pickable=True),
    ]
    view = pdk.ViewState(latitude=40, longitude=65, zoom=1.4)
    st.pydeck_chart(pdk.Deck(layers=layers, initial_view_state=view, map_style=pdk.map_styles.CARTO_LIGHT, tooltip={"text": "{label}"}), height=520)
    st.caption("남색 = 기존 공장, 파랑 = 선택한 신규 공장, 회색 점 = OEM 고객 (크기 = 수요), 선 굵기 = 공급 물량. 선은 시각화용이며 계산은 레인 데이터 사용.")
    st.dataframe(F[F.state != "미선택"][["label", "state", "gwh"]].rename(columns={"label": "공장", "state": "구분", "gwh": f"{year} 공급 GWh"}),
                 hide_index=True, width="stretch")

# ------------------------------------------------------------------ ③ 도착원가
with tabs[2]:
    st.subheader("kWh당 도착원가: 오창과 브로츠와프는 2026년 동률, 탄소 규제가 강해지면 격차가 벌어진다")
    cc = st.columns(3)
    cust = cc[0].selectbox("고객", list(M.D.index), index=0, format_func=lambda d: DN[d])
    yr = cc[1].selectbox("연도", [2026, 2030, 2035, 2040, 2045], index=0)
    sc1 = cc[2].selectbox("시나리오 ", ["base", "high", "onshore"], format_func=lambda s: SC[s])
    rows = []
    for p in C.EXISTING + cands:
        u = M.unit_cost(p, cust, yr, Options(scen=sc1))
        fixed = M.fixed_opex(p, yr, Options()) / max(M.capacity(p, yr, Options()), 1e-9) if M.capacity(p, yr, Options()) > 0 else None
        rows.append(dict(공장=NAME[p], **{k: round(v, 2) for k, v in u["items"].items()}, 도착원가=round(u["total"], 2),
                         판매가격=round(u["price"], 2), 공헌이익=round(u["margin"], 2),
                         **{"kWh당 고정비": None if fixed is None else round(fixed, 2)}, 리드타임일=u["lead_time"]))
    tb = pd.DataFrame(rows)
    fig = go.Figure()
    items = ["소재비", "가공비", "전력비", "운송·하역비", "관세", "재고유지비", "CBAM", "OEM 내부 탄소가격", "역내생산 불이익"]
    palette = ["#1F3864", "#2F6BD8", "#7096DB", "#A9BFE8", "#6B7280", "#9CA3AF", "#C00000", "#E57373", "#F4B183"]
    for it, col in zip(items, palette):
        if tb[it].abs().sum() > 0:
            fig.add_bar(y=tb["공장"], x=tb[it], name=it, orientation="h", marker_color=col)
    fig.update_layout(barmode="relative", height=120 + 50 * len(tb), margin=dict(l=10, r=10, t=10, b=10),
                      xaxis_title="$/kWh", legend=dict(orientation="h", y=-0.25), plot_bgcolor="white")
    st.plotly_chart(fig, width="stretch")
    st.dataframe(tb, hide_index=True, width="stretch")
    st.caption("도착원가 = 변동비 (고정운영비·감가상각 제외). 자료 11 재현: 2026 볼프스부르크 오창 86.40 / 브로츠와프 86.24 $/kWh.")

# ------------------------------------------------------------------ ④ 배정
with tabs[3]:
    st.subheader(f"{year}년 최적 배정 (LP) · {SC[scen]}")
    alloc, shadow, obj, dem = allocate_cached(plants, year, scen, decarb, dec_from)
    alloc = alloc.assign(region=alloc.demand.map(region))
    pv = alloc.pivot_table(index="plant", columns="region", values="gwh", aggfunc="sum", fill_value=0)
    pv["합계"] = pv.sum(axis=1)
    pv["생산능력"] = [M.capacity(p, year, Options()) for p in pv.index]
    pv["잠재가격 $/kWh/년"] = [round(shadow.get(p, 0), 2) for p in pv.index]
    pv.index = pv.index.map(NAME)
    c1, c2 = st.columns([3, 2])
    c1.dataframe(pv.round(1), width="stretch")
    near = M.nearest(list(plants), year, Options(scen=scen))
    c2.markdown("**최근접 배정과 비교 (생산능력 무시)**")
    c2.dataframe(pd.DataFrame({"최근접 배정 GWh": {NAME[p]: round(v, 1) for p, v in near.items()},
                               "생산능력": {NAME[p]: M.capacity(p, year, Options()) for p in plants}}), width="stretch")
    addr = (C.DUAL_SOURCING * dem)
    eu_ids = [d for d in M.D.index if d.startswith("D_EU")]
    served = alloc.groupby("demand").gwh.sum()
    m1, m2, m3 = st.columns(3)
    m1.metric("공략 가능 수요 (70%)", f"{addr.sum():.1f} GWh")
    m2.metric("실제 공급 / 공급률", f"{served.sum():.1f} GWh", f"{served.sum()/addr.sum()*100:.0f}%")
    m3.metric("유럽 공급률", f"{served.reindex(eu_ids).fillna(0).sum()/addr[eu_ids].sum()*100:.0f}%")
    st.markdown("**고객별 공급 비중 (고객 수요 대비, 상한 70%)**")
    cust_tb = alloc.pivot_table(index="demand", columns="plant", values="gwh", aggfunc="sum", fill_value=0)
    cust_tb = cust_tb.reindex(M.D.index).fillna(0)
    cust_tb["공급 비중 %"] = (cust_tb.sum(axis=1) / dem * 100).round(0)
    cust_tb.columns = [NAME.get(c, c) for c in cust_tb.columns]
    cust_tb.index = cust_tb.index.map(DN)
    st.dataframe(cust_tb.round(1), width="stretch", height=420)
    st.caption("잠재가격 = 생산능력 1GWh를 늘릴 때 늘어나는 연간 공헌이익 (백만 달러/GWh = $/kWh). 신규 공장 연간 비용(자본비용+고정비, 데브레첸 약 16.3)보다 크면 증설 신호.")

# ------------------------------------------------------------------ ⑤ 탄소
with tabs[4]:
    st.subheader("위치기반으로 바뀌면 브로츠와프·오창은 유럽 공급 자격을 잃는다")
    rows = []
    o = Options(scen="cap", decarb=dict(decarb), decarb_from=dec_from)
    for p in C.EXISTING + C.CANDIDATES:
        eu = [d for d in M.D.index if d.startswith("D_EU")]
        fps = [M.footprint(p, d, 2045, o) for d in eu]
        mkt = fps[0][0]; loc = fps[0][1]
        totals = [f[1] + f[2] for f in fps]
        r = M.F.loc[p]
        rows.append({"공장": NAME[p], "전력 탄소집약도": r.grid_intensity_kgco2_per_kwh, "재생에너지 조달 %": r.renewable_share * 100,
                     "시장기반": round(mkt, 1), "위치기반": round(loc, 1),
                     "위치기반+운송 (범위)": f"{min(totals):.1f}~{max(totals):.1f}",
                     "2030 65kg 통과 고객": f"{sum(t <= 65 for t in totals)} / 12", "2035 60kg 통과 고객": f"{sum(t <= 60 for t in totals)} / 12"})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    g = M.F.loc[C.WROCLAW].grid_intensity_kgco2_per_kwh
    base_loc = M.footprint(C.WROCLAW, "D_EU_SE_VOLVO_GOTHENBURG")[1] + M.footprint(C.WROCLAW, "D_EU_SE_VOLVO_GOTHENBURG")[2]
    need = {cap: max(0, (base_loc - cap) / (C.ELEC_KWH_PER_KWH_CELL * g)) for cap in (65, 60)}
    k1, k2, k3 = st.columns(3)
    k1.metric("브로츠와프 필요 저탄소 전력 · 2030 (65kg)", f"{need[65]*100:.0f}%")
    k2.metric("브로츠와프 필요 저탄소 전력 · 2035 (60kg)", f"{need[60]*100:.0f}%")
    k3.metric("현재 설정 (사이드바)", f"{dec*100:.0f}%", f"{dec_from}년부터")
    st.caption("위치기반 = 시장기반 + 38.8 × 전력 탄소집약도 × 재생에너지 비중 (PPA·GO 불인정, 자료 6 주석). 직접 연결 저탄소 전력은 위치기반에서도 인정된다고 가정. "
               "필요 비중은 가장 먼 유럽 고객 기준. 사이드바 탈탄소화 값이 표의 위치기반에 반영된다.")

# ------------------------------------------------------------------ ⑥ 투자 평가
with tabs[5]:
    st.subheader("공장 단위 NPV는 잠식을 무시한다 — 이사회에는 네트워크 증분 NPV를 올린다")
    sc4 = st.radio("시나리오", ["base", "cap", "high", "slow", "onshore"], format_func=lambda s: SC[s], horizontal=True)
    with st.spinner("후보지 8곳 20년 NPV 계산 중…"):
        rows = []
        for c in C.CANDIDATES:
            cf = cashflows_cached(tuple(C.EXISTING + [c]), sc4)
            rows.append({"후보지": NAME[c], "공장 단위 NPV": round(cf[cf.plant == c].pv.sum()),
                         "네트워크 증분 NPV": round(inc((c,), sc4))})
    tb = pd.DataFrame(rows); tb["잠식 효과"] = tb["네트워크 증분 NPV"] - tb["공장 단위 NPV"]
    fig = go.Figure()
    fig.add_bar(y=tb["후보지"], x=tb["공장 단위 NPV"], name="공장 단위 NPV", orientation="h", marker_color=LGRAY)
    fig.add_bar(y=tb["후보지"], x=tb["네트워크 증분 NPV"], name="네트워크 증분 NPV", orientation="h",
                marker_color=[BLUE if v > 0 else GRAY for v in tb["네트워크 증분 NPV"]])
    fig.update_layout(barmode="group", height=420, xaxis_title="백만 달러 (20년, 2026년 가치)", margin=dict(l=10, r=10, t=10, b=10),
                      legend=dict(orientation="h", y=-0.2), plot_bgcolor="white")
    st.plotly_chart(fig, width="stretch")
    st.dataframe(tb, hide_index=True, width="stretch")
    st.markdown("**선택한 구성의 연도별 회사 전체 현금흐름**")
    cf = cashflows_cached(plants, sc4, decarb, dec_from)
    yearly = cf.groupby("year")[["ebitda", "tax", "capex", "cf"]].sum()
    fig2 = go.Figure()
    fig2.add_bar(x=yearly.index, y=yearly.cf, marker_color=[BLUE if v > 0 else GRAY for v in yearly.cf], name="현금흐름")
    fig2.update_layout(height=300, yaxis_title="백만 달러", margin=dict(l=10, r=10, t=10, b=10), plot_bgcolor="white")
    st.plotly_chart(fig2, width="stretch")
    st.caption(f"선택 구성 회사 전체 NPV: {cf.pv.sum():,.0f}백만 달러. 공장 단위 = 신규 공장 자체 현금흐름(자료 13 방식), 증분 = 회사 전체 차이(자료 14 방식).")

# ------------------------------------------------------------------ ⑦ 시나리오·실물옵션
with tabs[6]:
    st.subheader("어떤 확률에서도 데브레첸이 기대값 1위·최대후회 최소다")
    OPTS = {"현행 유지": (), **{NAME[c]: (c,) for c in C.CANDIDATES},
            "데브레첸 + 사라고사": ("F_EU_HU_DEBRECEN", "F_EU_ES_ZARAGOZA")}
    S = ["base", "high", "cap", "slow", "onshore"]
    with st.spinner("시나리오 5개 × 투자안 10개 행렬 계산 중 (첫 실행 시 약 1분)…"):
        mat = pd.DataFrame({SC[s]: {k: (0.0 if not v else inc(v, s)) for k, v in OPTS.items()} for s in S})
    st.markdown("**발생 확률 (%)** — 합계는 자동으로 100%로 맞춤")
    pc = st.columns(5)
    w = [pc[i].number_input(SC[s], 0, 100, 20, 5, key=f"p_{s}") for i, s in enumerate(S)]
    w = pd.Series(w, index=mat.columns, dtype=float); w = w / w.sum() if w.sum() > 0 else w
    ev = (mat * w).sum(axis=1); regret = (mat.max() - mat).max(axis=1)
    out = mat.round(0).assign(**{"기대 NPV": ev.round(0), "최대후회": regret.round(0)}).sort_values("기대 NPV", ascending=False)
    st.dataframe(out.style.format("{:,.0f}").background_gradient(subset=["기대 NPV"], cmap="Blues"), width="stretch")
    st.caption("백만 달러, 기존 네트워크 대비 20년 증분 NPV. 최대후회 = 각 시나리오의 최선안 대비 손해의 최댓값.")

    st.markdown("### 브로츠와프 탈탄소화 손익분기")
    d35 = st.slider("탈탄소화 비중", 10, 50, 35, 1, format="%d%%", key="d35") / 100
    v_dec = inc((), "cap", ((C.WROCLAW, d35),), 2030)
    p2 = st.slider("강한 규제(ver2)가 올 확률", 0, 100, 20, 5, format="%d%%") / 100
    b1, b2 = st.columns(2)
    b1.metric("ver2에서 탈탄소화 가치 (비용 전)", fmt_m(v_dec))
    b2.metric("탈탄소화에 써도 되는 최대 금액", f"{v_dec * p2 / 100:,.1f}억$", help="= ver2 가치 × ver2 확률 (ver1에서는 가치 0)")
    lag = pd.DataFrame({"확보 연도": [2030, 2032, 2035],
                        "ver2 가치 (억$)": [round(inc((), "cap", ((C.WROCLAW, d35),), y) / 100, 1) for y in (2030, 2032, 2035)]})
    st.dataframe(lag, hide_index=True)

    st.markdown("### 데브레첸: 지금 확정 vs 2028년 결정 (2년 지연)")
    now = mat.loc[NAME["F_EU_HU_DEBRECEN"]]
    wait = pd.Series({SC[s]: max(0.0, inc(("F_EU_HU_DEBRECEN",), s, delay=2)) for s in S})
    cmp_tb = pd.DataFrame({"지금 확정": now.round(0), "2028년 결정 (불리하면 안 지음)": wait.round(0)})
    st.dataframe(cmp_tb.style.format("{:,.0f}"), width="stretch")
    e_now, e_wait = (now * w).sum(), (wait * w).sum()
    st.metric("현재 확률에서 더 나은 선택", "지금 확정" if e_now >= e_wait else "2028년 결정",
              f"지금 {e_now:,.0f} vs 2028년 {e_wait:,.0f} (백만 달러)")
    st.caption("권고: 지금은 입찰 대응 수준까지 준비하고, 2027년 초 수요·수주·헝가리 정책을 확인해 본투자 확정 (단계적 확정).")

# ------------------------------------------------------------------ ⑧ 검증
with tabs[7]:
    st.subheader("시뮬레이터는 케이스 자료의 수치를 재현한다")
    o = Options()
    v11 = pd.DataFrame({"항목": ["오창 → 볼프스부르크 2026", "브로츠와프 → 볼프스부르크 2026"],
                        "케이스 (자료 11)": [86.40, 86.24],
                        "시뮬레이터": [round(M.unit_cost(C.OCHANG, "D_EU_DE_VW_WOLFSBURG", 2026, o)["total"], 2),
                                  round(M.unit_cost(C.WROCLAW, "D_EU_DE_VW_WOLFSBURG", 2026, o)["total"], 2)]})
    st.markdown("**자료 11 도착원가 ($/kWh)**"); st.dataframe(v11, hide_index=True)
    case14 = {"base": [-365, 263, -2083, -997, -167, -2046, -798, -511], "cap": [-3680, 2336, -166, 521, 1311, -608, 305, 907]}
    if st.button("자료 14 증분 NPV 검증 실행 (ver1·ver2, 16개 값)"):
        with st.spinner("계산 중…"):
            rows = []
            for s, vals in case14.items():
                for c, e in zip(C.CANDIDATES, vals):
                    rows.append({"시나리오": SC[s], "후보지": NAME[c], "케이스 (자료 14)": e, "시뮬레이터": round(inc((c,), s))})
            vt = pd.DataFrame(rows); vt["차이"] = vt["시뮬레이터"] - vt["케이스 (자료 14)"]
        st.dataframe(vt, hide_index=True, width="stretch")
        st.success(f"최대 차이 {vt['차이'].abs().max()}백만 달러")
    st.caption("전체 48개 값(자료 11·2·13·14, 시나리오 5개) 검증: tests/test_regression.py")
