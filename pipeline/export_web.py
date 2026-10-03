"""导出建站数据：分析 JSON + 路线内容库 → site/src/data/。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from roadmaps import BACKGROUNDS, PROFILE_INTROS, ROUTES
from skills_dict import skill_dicts

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "processed" / "analysis"
DST = ROOT / "site" / "src" / "data"


def main() -> None:
    DST.mkdir(parents=True, exist_ok=True)
    for f in SRC.glob("*.json"):
        shutil.copy(f, DST / f.name)
    for f in (SRC / "profiles").glob("*.json"):
        shutil.copy(f, DST / f"profile_{f.name}")
    (DST / "roadmaps.json").write_text(json.dumps({
        "routes": ROUTES, "backgrounds": BACKGROUNDS, "intros": PROFILE_INTROS,
    }, ensure_ascii=False))
    (DST / "skills_meta.json").write_text(json.dumps({
        "skills": skill_dicts(),
    }, ensure_ascii=False))
    print("exported:", sorted(p.name for p in DST.iterdir()))


if __name__ == "__main__":
    main()
