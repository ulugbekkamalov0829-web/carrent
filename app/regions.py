"""O'zbekiston hududlari va tumanlari: bitta manba — static/geo/regions.json (sahifalar ham shu faylni o'qiydi)."""
import json
from functools import lru_cache
from pathlib import Path

FILE = Path(__file__).resolve().parent.parent / "static" / "geo" / "regions.json"


@lru_cache(maxsize=1)
def _data() -> dict:
    return json.loads(FILE.read_text(encoding="utf-8"))


def regions() -> dict[str, list[str]]:
    return {r["key"]: r["districts"] for r in _data()["regions"]}


def normalize_region(name: str | None) -> str | None:
    """Eski yozuvlar ("Toshkent") va katta-kichik harf farqini kanonik nomga keltiradi. Noma'lum bo'lsa None."""
    if not name:
        return None
    name = name.strip().replace("ʻ", "'").replace("ʼ", "'").replace("‘", "'").replace("’", "'")
    by_lower = {k.lower(): k for k in regions()}
    if name.lower() in by_lower:
        return by_lower[name.lower()]
    return _data()["aliases"].get(name) or _data()["aliases"].get(name.replace("'", ""))


def valid_district(region: str, district: str | None) -> bool:
    return district is None or district in regions().get(region, [])
