"""把 ECharts 发行版下载到站点 public/（经 safe_fetch 白名单通道，jsdelivr）。"""

from pathlib import Path

from config import safe_fetch

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site" / "public" / "echarts.min.js"
URL = "https://cdn.jsdelivr.net/npm/echarts@5.6.0/dist/echarts.min.js"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    data = safe_fetch(URL, binary=True)
    OUT.write_bytes(data)
    print(f"saved {OUT} ({len(data)} bytes)")


if __name__ == "__main__":
    main()
