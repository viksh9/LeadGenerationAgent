"""One-off safe company de-duplication (remediation).

Merges companies that share a normalized_name into a single canonical row:
  * survivor = the company a Lead points to (else highest data_trust, else max id)
  * every company_id FK on other tables is re-pointed loser -> survivor
  * the now-dereferenced empty duplicate rows are deleted
All in one transaction. Real lead/evidence/contact data is preserved; only
confirmed-duplicate company shells are removed (§4/§5). A DB backup should be taken
first (data/leads.db.bak-*). Idempotent: re-running when there are no duplicates is a no-op.
"""

from __future__ import annotations

import sqlite3
import sys
from collections import defaultdict

DB = sys.argv[1] if len(sys.argv) > 1 else "data/leads.db"


def main() -> int:
    con = sqlite3.connect(DB)
    con.execute("PRAGMA foreign_keys=OFF")
    cur = con.cursor()

    fk_tables = [r[0] for r in con.execute("select name from sqlite_master where type='table'")
                 if "company_id" in [c[1] for c in con.execute(f"PRAGMA table_info('{r[0]}')")]]

    rows = cur.execute("select id, normalized_name, coalesce(data_trust_score,0) from companies "
                       "where normalized_name is not null and normalized_name!=''").fetchall()
    byname: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for cid, nn, dt in rows:
        byname[nn].append((cid, dt))
    dups = {nn: v for nn, v in byname.items() if len(v) > 1}

    lead_cids = {r[0] for r in cur.execute(
        "select distinct company_id from leads where company_id is not null")}

    losers: list[int] = []
    for nn, members in dups.items():
        ids = [cid for cid, _ in members]
        lead_owned = [cid for cid in ids if cid in lead_cids]
        survivor = lead_owned[0] if lead_owned else sorted(members, key=lambda t: (t[1], t[0]))[-1][0]
        for cid in ids:
            if cid != survivor:
                losers.append(cid)
                for t in fk_tables:
                    cur.execute(f"UPDATE {t} SET company_id=? WHERE company_id=?", (survivor, cid))

    cur.executemany("DELETE FROM companies WHERE id=?", [(l,) for l in losers])
    con.commit()
    print(f"merged {len(dups)} duplicate name-group(s); removed {len(losers)} duplicate company shell(s)")

    one = lambda q: con.execute(q).fetchone()[0]
    print("companies now =", one("select count(*) from companies"))
    print("leads now     =", one("select count(*) from leads"))
    print("duplicate normalized_names remaining =", one(
        "select count(*) from (select normalized_name from companies "
        "where normalized_name is not null and normalized_name!='' "
        "group by normalized_name having count(*)>1)"))
    print("leads pointing at a missing company  =", one(
        "select count(*) from leads where company_id is not null "
        "and company_id not in (select id from companies)"))
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
