"""
apply_additions.py  —  reload_from_cypher.py의 비파괴(DETACH DELETE 없음) 버전.
이미 떠 있는 그래프에 새 노드/관계를 "얹기"만 한다. 기존 데이터는 건드리지 않는다.

사용: python apply_additions.py <cypher_file_path>
"""

import sys
import os

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "manager_ai_core", "kg_mapping"))
from graph_retrieval import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
from neo4j import GraphDatabase


def apply(cypher_path: str):
    with open(cypher_path, encoding="utf-8") as f:
        lines = f.readlines()

    clean_lines = [l for l in lines if l.strip() and not l.strip().startswith("//")]
    text = "".join(clean_lines)
    statements = [s.strip() for s in text.split(";") if s.strip()]
    print(f"{len(statements)} statements parsed from {cypher_path}")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD), notifications_min_severity="OFF")
    with driver.session() as session:
        before = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        print(f"nodes before: {before}")

        ok, failed = 0, []
        last_result = None
        for i, stmt in enumerate(statements):
            try:
                res = session.run(stmt)
                if stmt.strip().upper().startswith("MATCH") and "RETURN" in stmt.upper():
                    last_result = res.data()
                ok += 1
            except Exception as e:
                failed.append((i, stmt[:150], str(e)[:300]))

        print(f"executed ok: {ok}/{len(statements)}")
        for i, stmt, err in failed:
            print(f"FAILED [{i}]: {stmt}\n  -> {err}")

        after = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        print(f"nodes after: {after}")

        if last_result:
            print("\n검증 쿼리 결과:")
            for row in last_result:
                print(" ", row)
    driver.close()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    if len(sys.argv) != 2:
        print("usage: python apply_additions.py <cypher_file_path>")
        sys.exit(1)

    apply(sys.argv[1])
