#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Write the full title back into works whose `name` is a hard-cut prefix of `title`.

The report already shows `title` in the works table. This only repairs the data.
A real short name (SciMON, CRESt, the clause before ':') is left alone.

  python scripts/repair_work_names.py surveys/agent-science-bio-drug-2026-10-21/works.json
  python scripts/repair_work_names.py surveys/agent-science-bio-drug-2026-10-21/works.json --write

Without --write or -o the command prints the rows it would change and does not touch the file.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from work_names import is_hard_truncated_name, repair_works  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("works_json", help="path to works.json")
    ap.add_argument("--write", action="store_true", help="replace hard-cut names in this file")
    ap.add_argument("-o", "--out", help="write the repaired JSON to this path")
    a = ap.parse_args()
    works = json.load(open(a.works_json, encoding="utf-8"))
    if not isinstance(works, list):
        sys.exit("works.json must be a list")
    fixed, n = repair_works(works)
    print(f"{n} hard-cut name(s) of {len(works)}")
    for old, new in zip(works, fixed):
        if old.get("name") != new.get("name"):
            print(f"  {old.get('name')!r}")
            print(f"    -> {new.get('name')!r}")
    if not a.write and not a.out:
        if n:
            print("dry run. pass --write to update the file, or -o PATH to write a copy")
        return
    dest = a.out or a.works_json
    os.makedirs(os.path.dirname(os.path.abspath(dest)) or ".", exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(fixed, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
