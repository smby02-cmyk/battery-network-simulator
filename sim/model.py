"""한누리 배터리 공급망 시뮬레이터 — 계산 엔진.

모듈 구성 (design.md 3장)
  1. 원가     unit_cost()          레인별 kWh당 도착원가 항목
  2. 탄소     footprint()          시장기반·위치기반 탄소발자국, ver2 상한 판정
  3. 배정     allocate()           연도별 LP (HiGHS): 생산능력·70% 상한·상한 위반 레인 차단
  4. 재무     npv()                2026–2045 회사 전체 현금흐름 → NPV
  5. 리스크   (app.py)             시나리오 × 투자안 행렬, 기대값·최대후회·손익분기
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import highspy
import pandas as pd

from . import config as C


@dataclass
class Options:
    """시나리오와 정책 옵션."""
    scen: str = "base"                       # base / cap / high / slow / onshore
    decarb: dict = field(default_factory=dict)   # {공장: 직접 연결 저탄소 전력 비중}
    decarb_from: int = 2030                  # 저탄소 전력 확보 연도
    delay: int = 0                           # 신규 공장 투자 지연(년)

    def key(self):
        return (self.scen, tuple(sorted(self.decarb.items())), self.decarb_from, self.delay)


class Model:
    def __init__(self, xlsx: str = C.DATA_FILE):
        f = pd.read_excel(xlsx, sheet_name=None)
        self.F = f["Factories"].set_index("factory_id")
        self.D = f["Demand_Nodes"].set_index("demand_id")
        self.L = f["Factory_Demand_Lanes"].set_index(["factory_id", "demand_id"])
        self.T = f["Transport_Params"]
        self._cost = {}   # (p, d, y, scen) -> unit_cost 결과 캐시 (네트워크·탈탄소화와 무관)

    # ------------------------------------------------------------ 일정
    def ramp(self, p, y, o: Options):
        if p in C.EXISTING:
            return 1.0
        y -= o.delay
        if p == C.WROCLAW_EXP:
            return C.EXPANSION_RAMP.get(y, 1.0 if y > max(C.EXPANSION_RAMP) else 0.0)
        return C.GREENFIELD_RAMP.get(y, 1.0 if y > max(C.GREENFIELD_RAMP) else 0.0)

    def capacity(self, p, y, o: Options):
        if p == C.OCHANG:
            return 35.0
        if p == C.WROCLAW:
            return 86.0 if y < 2028 else 90.0
        return self.ramp(p, y, o) * float(self.F.loc[p].target_capacity_gwh_yr)

    def capex_share(self, p, y, o: Options):
        if p in C.EXISTING:
            return 0.0
        sched = C.EXPANSION_CAPEX if p == C.WROCLAW_EXP else C.GREENFIELD_CAPEX
        return sched.get(y - o.delay, 0.0)

    def start_year(self, p, o: Options):
        return (C.EXPANSION_START if p == C.WROCLAW_EXP else C.GREENFIELD_START) + o.delay

    def fixed_opex(self, p, y, o: Options):
        base = float(self.F.loc[p].fixed_opex_usd_million_per_yearr) * (1 + C.FIXED_OPEX_GROWTH) ** (y - C.BASE_YEAR)
        if p in C.EXISTING:
            return base
        r = self.ramp(p, y, o)
        if r == 0:
            return 0.0
        return base * (max(r, C.RAMP_MIN_FIXED) if r < 1 else 1.0)

    # ------------------------------------------------------------ 수요·가격
    @staticmethod
    def _decline(y, rates):
        return rates[0] ** (min(y, 2030) - C.BASE_YEAR) * rates[1] ** max(y - 2030, 0)

    def demand(self, y, o: Options):
        k = C.SLOW_GROWTH_MULT if o.scen == "slow" else 1.0
        g1, g2 = min(y, 2030) - C.BASE_YEAR, max(y - 2030, 0)
        return (self.D.annual_ev_battery_demand_GWh_2026 * (1 + k * self.D.growth_rate_2026_2030) ** g1
                * (1 + k * self.D.growth_rate_2031_2045) ** g2)

    def price(self, y):
        return self.D.purchase_price_usd_per_kwh_2026 * self._decline(y, C.PRICE_DECLINE)

    def carbon_price(self, y, o: Options):
        cp = C.CARBON_PRICE_2026 * (1 + C.CARBON_PRICE_GROWTH) ** (y - C.BASE_YEAR)
        return cp * (C.HIGH_CARBON_MULT if o.scen == "high" else 1.0)

    # ------------------------------------------------------------ 2. 탄소
    def footprint(self, p, d, y=None, o: Options | None = None):
        """(시장기반, 위치기반, 운송배출) kg/kWh. 위치기반은 직접 연결 저탄소 전력만 차감."""
        ln = self.L.loc[(p, d)]; r = self.F.loc[p]
        mkt = float(ln.product_embedded_co2e_kg_per_kwh_proxy)
        grid = C.ELEC_KWH_PER_KWH_CELL * r.grid_intensity_kgco2_per_kwh
        loc = mkt + grid * r.renewable_share
        if o is not None and y is not None and y >= o.decarb_from:
            loc -= grid * o.decarb.get(p, 0.0)
        return mkt, loc, float(ln.transport_co2e_kg_per_kwh_finished_pack)

    def cap_ok(self, p, d, y, o: Options):
        if o.scen != "cap" or not d.startswith("D_EU") or y < C.POLICY_YEAR:
            return True
        _, loc, tr = self.footprint(p, d, y, o)
        return loc + tr <= (C.CAP_2030 if y < 2035 else C.CAP_2035)

    # ------------------------------------------------------------ 1. 원가
    def unit_cost(self, p, d, y, o: Options):
        """레인별 kWh당 원가 항목 ($/kWh)."""
        key = (p, d, y, o.scen)
        if key not in self._cost:
            self._cost[key] = self._unit_cost(p, d, y, o)
        return self._cost[key]

    def _unit_cost(self, p, d, y, o: Options):
        r = self.F.loc[p]; ln = self.L.loc[(p, d)]
        mat = C.MATERIAL_2026 * self._decline(y, C.MATERIAL_DECLINE) / r.yield_rate
        cv = r.conversion_cost_usd_per_kwh_ex_material * C.CONVERSION_LEARNING ** min(y - C.BASE_YEAR, C.CONVERSION_LEARNING_YEARS)
        el = C.ELEC_KWH_PER_KWH_CELL * r.electricity_price_usd_per_kwh
        inv = C.INVENTORY_RATE * (ln.lead_time_days + C.SAFETY_STOCK_DAYS) / 365 * (mat + cv)
        pr = float(self.price(y)[d])
        tar = pr * ln.tariff_pct_of_customs_value / 100
        kr_eu = p.startswith("F_KR") and d.startswith("D_EU")
        cp = self.carbon_price(y, o)
        share = 1.0 if (o.scen == "high" and y >= C.POLICY_YEAR) else C.CBAM_SHARE_BASE
        cbam = ln.product_embedded_co2e_kg_per_kwh_proxy * share * cp * C.EUR_USD / 1000 if kr_eu else 0.0
        oem = 0.0
        if o.scen == "high" and d.startswith("D_EU"):
            fp = ln.product_embedded_co2e_kg_per_kwh_proxy + ln.transport_co2e_kg_per_kwh_finished_pack
            oem = (fp - C.OEM_INTERNAL_THRESHOLD) * cp * C.EUR_USD / 1000
        policy = C.ONSHORE_PENALTY if (o.scen == "onshore" and kr_eu and y >= C.POLICY_YEAR) else 0.0
        items = {"소재비": mat, "가공비": cv, "전력비": el, "운송·하역비": float(ln.freight_cost_usd_per_kwh_finished_pack),
                 "관세": tar, "재고유지비": inv, "CBAM": cbam, "OEM 내부 탄소가격": oem, "역내생산 불이익": policy}
        total = sum(items.values())
        return dict(items=items, total=total, price=pr, margin=pr - total, lead_time=float(ln.lead_time_days))

    # ------------------------------------------------------------ 3. 배정
    def allocate(self, plants, y, o: Options):
        """연도별 LP. 반환: 배정표(DataFrame), 잠재가격, 공헌이익 합계."""
        live = [p for p in plants if self.capacity(p, y, o) > 0]
        dem = self.demand(y, o)
        m = {}
        for p in live:
            for d in self.D.index:
                if self.cap_ok(p, d, y, o):
                    m[(p, d)] = self.unit_cost(p, d, y, o)["margin"]
        h = highspy.Highs(); h.setOptionValue("output_flag", False)
        x = {k: h.addVariable(lb=0) for k in m}
        rows = {}
        for p in live:
            ks = [k for k in m if k[0] == p]
            if ks:
                rows[p] = h.addConstr(sum(x[k] for k in ks) <= self.capacity(p, y, o))
        for d in self.D.index:
            ks = [k for k in m if k[1] == d]
            if ks:
                h.addConstr(sum(x[k] for k in ks) <= C.DUAL_SOURCING * float(dem[d]))
        h.maximize(sum(m[k] * x[k] for k in m))
        duals = h.getSolution().row_dual
        recs = [dict(plant=k[0], demand=k[1], gwh=h.val(v), margin=m[k]) for k, v in x.items() if h.val(v) > 1e-6]
        alloc = pd.DataFrame(recs, columns=["plant", "demand", "gwh", "margin"])
        shadow = {p: abs(duals[c.index]) for p, c in rows.items()}
        return alloc, shadow, float(h.getObjectiveValue()), dem

    def nearest(self, plants, y, o: Options):
        """비교용 최근접 배정 (생산능력 무시)."""
        def hav(a, b, c, d):
            a, b, c, d = map(math.radians, (a, b, c, d))
            return 2 * 6371 * math.asin(math.sqrt(math.sin((c - a) / 2) ** 2 + math.cos(a) * math.cos(c) * math.sin((d - b) / 2) ** 2))
        dem = self.demand(y, o); out = {p: 0.0 for p in plants}
        for d, r in self.D.iterrows():
            best = min(plants, key=lambda p: hav(self.F.loc[p].latitude, self.F.loc[p].longitude, r.latitude, r.longitude))
            out[best] += C.DUAL_SOURCING * float(dem[d])
        return out

    # ------------------------------------------------------------ 4. 재무
    def cashflows(self, plants, o: Options):
        rows = []
        for y in C.YEARS:
            alloc, _, _, _ = self.allocate(plants, y, o)
            contrib = alloc.assign(c=alloc.gwh * alloc.margin).groupby("plant").c.sum()
            vol = alloc.groupby("plant").gwh.sum()
            eu = alloc[alloc.demand.str.startswith("D_EU")].groupby("plant").gwh.sum()
            for p in plants:
                ebitda = float(contrib.get(p, 0.0)) - self.fixed_opex(p, y, o)
                dep = capex = 0.0
                if p not in C.EXISTING:
                    net = float(self.F.loc[p].capex_usd_million) * (1 - C.SUBSIDY[p])
                    capex = net * self.capex_share(p, y, o)
                    s = self.start_year(p, o)
                    if s <= y < s + C.DEPRECIATION_YEARS:
                        dep = net / C.DEPRECIATION_YEARS
                tax = max(ebitda - dep, 0.0) * C.TAX[p]
                cf = ebitda - tax - capex
                rows.append(dict(year=y, plant=p, gwh=float(vol.get(p, 0.0)), eu_gwh=float(eu.get(p, 0.0)),
                                 contribution=float(contrib.get(p, 0.0)), ebitda=ebitda, tax=tax, capex=capex,
                                 cf=cf, pv=cf / (1 + C.WACC) ** (y - C.BASE_YEAR)))
        return pd.DataFrame(rows)

    def npv(self, plants, o: Options):
        return float(self.cashflows(plants, o).pv.sum())

    def incremental_npv(self, add, o: Options, base_npv=None):
        """네트워크 증분 NPV = (기존 + add) − 기존. 탈탄소화는 o.decarb로."""
        base = base_npv if base_npv is not None else self.npv(C.EXISTING, Options(scen=o.scen))
        return self.npv(C.EXISTING + list(add), o) - base
