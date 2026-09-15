"""
load_v5.py  —  v5 스키마+seed 4개 파일을 순서대로 새 Neo4j 인스턴스(lifecareDB)에 적재한다.

reload_from_cypher.py는 파일 하나만 받아 통째로 DETACH DELETE 후 재적재하는 용도라,
v5는 4개 파일(제약 -> seed -> additions -> runtime_examples)을 순서 그대로 이어붙여야 해서
전용 스크립트로 분리했다. UTF-8 손상을 피하려고 cypher-shell 대신 파이썬 드라이버로
문장 단위 실행한다(2026-08-29 결정 - 한글 rationale 인코딩 손상 사고 재발 방지).

실행:
    python load_v5.py            # .env가 있으면 비밀번호 자동, 없으면 NEO4J_PASSWORD 환경변수 사용
"""

import os
import sys
from neo4j import GraphDatabase

FILES = [
    "livingcare_graph_v5.cypher",
    "livingcare_graph_v5_seed.cypher",
    "livingcare_graph_v5_seed_additions.cypher",
    "livingcare_graph_v5_seed_runtime_examples.cypher",
    "livingcare_graph_v5_seed_comfort_setpoints.cypher",
    "livingcare_graph_v5_seed_response_protocols.cypher",
]


def _load_local_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


_load_local_env()

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD")
# lifecareDB는 dbms.security.auth_enabled=false로 인증을 꺼놨다 - 비밀번호 없이 접속.
NEO4J_AUTH = (NEO4J_USER, NEO4J_PASSWORD) if NEO4J_PASSWORD else None


def parse_statements(path: str):
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    clean = [l for l in lines if l.strip() and not l.strip().startswith("//")]
    text = "".join(clean)
    return [s.strip() for s in text.split(";") if s.strip()]


def main():
    base = os.path.dirname(os.path.abspath(__file__))
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH, notifications_min_severity="OFF")

    with driver.session() as session:
        before = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        print(f"nodes before load: {before}")
        if before > 0:
            session.run("MATCH (n) DETACH DELETE n")
            print("wiped existing nodes (fresh reload)")

        total_ok, total_fail = 0, 0
        for fname in FILES:
            path = os.path.join(base, fname)
            statements = parse_statements(path)
            print(f"\n--- {fname}: {len(statements)} statements ---")
            ok, failed = 0, []
            for i, stmt in enumerate(statements):
                try:
                    session.run(stmt)
                    ok += 1
                except Exception as e:
                    failed.append((i, stmt[:120], str(e)[:200]))
            print(f"  ok: {ok}/{len(statements)}")
            for i, stmt, err in failed:
                print(f"  FAILED [{i}]: {stmt}\n    -> {err}")
            total_ok += ok
            total_fail += len(failed)

        after = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        rels = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
        print(f"\n=== done: {total_ok} ok, {total_fail} failed across {len(FILES)} files ===")
        print(f"nodes after load: {after}, relationships: {rels}")

    driver.close()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
