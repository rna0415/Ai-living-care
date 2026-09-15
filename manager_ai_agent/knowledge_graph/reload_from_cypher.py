"""
reload_from_cypher.py  —  Neo4j를 비우고 .cypher 파일 하나로 재적재한다.

cypher-shell(콘솔 코드페이지에 의존)로 적재하면 한글이 깨질 수 있다 — 실제로
livingcare_graph_v2.cypher 최초 적재 때 rationale 필드가 U+FFFD로 손상됐던 적이
있다. 이 스크립트는 파일을 UTF-8로 직접 읽어 neo4j 파이썬 드라이버로 문장 단위
실행해 그 문제를 피한다.

사용: python reload_from_cypher.py <cypher_file_path>
"""

import sys
import os

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "manager_ai_core", "kg_mapping"))
from graph_retrieval import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
from neo4j import GraphDatabase


def reload_graph(cypher_path: str):
    with open(cypher_path, encoding="utf-8") as f:
        lines = f.readlines()

    clean_lines = [l for l in lines if l.strip() and not l.strip().startswith("//")]
    text = "".join(clean_lines)
    statements = [s.strip() for s in text.split(";") if s.strip()]
    print(f"{len(statements)} statements parsed from {cypher_path}")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD), notifications_min_severity="OFF")
    with driver.session() as session:
        before = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        print(f"nodes before wipe: {before}")

        session.run("MATCH (n) DETACH DELETE n")

        ok, failed = 0, []
        for i, stmt in enumerate(statements):
            try:
                session.run(stmt)
                ok += 1
            except Exception as e:
                failed.append((i, stmt[:120], str(e)[:200]))

        print(f"executed ok: {ok}/{len(statements)}")
        for i, stmt, err in failed:
            print(f"FAILED [{i}]: {stmt}\n  -> {err}")

        after = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        print(f"nodes after reload: {after}")
    driver.close()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    if len(sys.argv) != 2:
        print("usage: python reload_from_cypher.py <cypher_file_path>")
        sys.exit(1)

    reload_graph(sys.argv[1])
