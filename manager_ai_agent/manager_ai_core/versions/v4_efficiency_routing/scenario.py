# -*- coding: utf-8 -*-
"""v4_efficiency_routing/scenario.py — 같은 시나리오를 효율성 중심 라우터로 재현."""

import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from edge_router import EdgeRouter

MOCK = {"motion": 5.0, "heartrate": 38, "temperature": 22}


async def main():
    print("=" * 78)
    print('[v4 효율성 라우팅] "할머니 괜찮은지 확인해줘" 시나리오')
    router = EdgeRouter()

    print("\n-- 1차 호출(전부 캐시 미스 예상) --")
    results = await router.route_many(MOCK)
    total_cost = 0.0
    for slot, r in results.items():
        print(f"  {slot:12s} tier={r['tier']:12s} action={r['action']:28s} cost={r['cost_ms']}ms")
        total_cost += r["cost_ms"]
    print(f"  총 비용 추정: {total_cost:.2f}ms  {router.stats}")

    print("\n-- 2차 호출(같은 관측값 반복 — 전부 캐시 적중 기대) --")
    results2 = await router.route_many(MOCK)
    total_cost2 = 0.0
    for slot, r in results2.items():
        print(f"  {slot:12s} tier={r['tier']:12s} action={r['action']:28s} cost={r['cost_ms']}ms")
        total_cost2 += r["cost_ms"]
    print(f"  총 비용 추정: {total_cost2:.2f}ms  {router.stats}")
    print(f"  1차 대비 절감: {total_cost - total_cost2:.2f}ms ({(1 - total_cost2/total_cost)*100:.1f}%)")

    print("\n-- 3차: 컴파일 테이블에 없는 slot(폴백 경로 실증) --")
    r = await router.route("bathroom", 25)
    print(f"  bathroom tier={r['tier']} action={r['action']} cost={r['cost_ms']}ms")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    asyncio.run(main())
