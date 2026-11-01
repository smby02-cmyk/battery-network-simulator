"""회귀 테스트: 케이스 자료의 수치를 시뮬레이터가 재현하는지 확인한다.

실행: python -m pytest tests -q   (또는 python tests/test_regression.py)
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from sim import Model, Options, config as C

M = Model()
CANDS = C.CANDIDATES
# 자료 13: 공장 단위 사업성 (기준)
CASE13 = [152, 1799, -366, -433, 263, -963, -558, 364]
# 자료 14: 네트워크 증분 NPV
CASE14 = {
    "base":    [-365, 263, -2083, -997, -167, -2046, -798, -511],
    "high":    [-159, 523, -1908, -706, 78, -1777, -598, -426],
    "cap":     [-3680, 2336, -166, 521, 1311, -608, 305, 907],
    "slow":    [-1365, -1206, -3367, -2065, -1195, -3053, -1473, -1357],
    "onshore": [-215, 456, -1902, -833, -9, -1907, -680, -375],
}
CASE14_BASE_NET = {"base": 15986, "high": 15711, "cap": 6132, "slow": 14916, "onshore": 15778}


def test_landed_cost_2026():
    """자료 11: 2026년 볼프스부르크 공급 도착원가."""
    o = Options()
    oc = M.unit_cost(C.OCHANG, "D_EU_DE_VW_WOLFSBURG", 2026, o)["total"]
    wr = M.unit_cost(C.WROCLAW, "D_EU_DE_VW_WOLFSBURG", 2026, o)["total"]
    assert abs(oc - 86.40) < 0.05 and abs(wr - 86.24) < 0.05, (oc, wr)


def test_allocation_2026():
    """자료 2: 2026년 공장별 지역 배정."""
    alloc, _, _, _ = M.allocate(C.EXISTING, 2026, Options())
    eu = alloc[alloc.demand.str.startswith("D_EU")].groupby("plant").gwh.sum()
    asia = alloc[alloc.demand.str.startswith("D_AS")].groupby("plant").gwh.sum()
    assert abs(eu.get(C.WROCLAW, 0) - 86.0) < 0.1
    assert abs(asia.get(C.OCHANG, 0) - 30.0) < 0.1


def test_case13_14():
    """자료 13·14: 후보지 8곳의 공장 단위 NPV와 시나리오 5개 증분 NPV (허용 오차 ±5백만 달러)."""
    for s, expected in CASE14.items():
        o = Options(scen=s)
        base = M.npv(C.EXISTING, o)
        assert abs(base - CASE14_BASE_NET[s]) / CASE14_BASE_NET[s] < 0.005, (s, base)
        for c, e in zip(CANDS, expected):
            inc = M.npv(C.EXISTING + [c], o) - base
            assert abs(inc - e) <= 5, (s, c, inc, e)
    o = Options()
    for c, e in zip(CANDS, CASE13):
        cf = M.cashflows(C.EXISTING + [c], o)
        assert abs(cf[cf.plant == c].pv.sum() - e) <= 5, (c, e)


if __name__ == "__main__":
    test_landed_cost_2026(); print("자료 11 OK")
    test_allocation_2026(); print("자료 2 OK")
    test_case13_14(); print("자료 13·14 OK (48개 값)")
