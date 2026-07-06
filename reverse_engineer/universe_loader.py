from __future__ import annotations
import json
from pathlib import Path

UNIVERSE_DIR = Path(__file__).resolve().parent.parent / "universe"
KNOWN_SLUGS: dict[str, str] = {
    "nifty50": "nifty50.json",
    "nifty500": "nifty500.json",
}


def _resolve_json_path(name_or_path: str) -> Path:
    p = Path(name_or_path)
    if p.exists() and p.suffix == ".json":
        return p.resolve()
    slug = name_or_path.strip().lower().replace(" ", "").replace("-", "").replace("_", "")
    fname = KNOWN_SLUGS.get(slug)
    if fname is not None:
        return (UNIVERSE_DIR / fname).resolve()
    alt = UNIVERSE_DIR / f"{slug}.json"
    if alt.exists():
        return alt.resolve()
    raise FileNotFoundError(
        f"Universe '{name_or_path}' not found. "
        f"Known slugs: {list(KNOWN_SLUGS.keys())}. "
        f"Or provide path to a JSON file, or comma-separated symbols."
    )


def load_universe(name_or_path: str) -> dict:
    json_path = _resolve_json_path(name_or_path)
    with open(json_path) as f:
        config = json.load(f)
    config["symbols"] = [c["symbol"] for c in config["constituents"]]
    return config


def get_symbols(name_or_path: str) -> list[str]:
    return load_universe(name_or_path)["symbols"]


def get_sector_map(name_or_path: str) -> dict[str, str]:
    config = load_universe(name_or_path)
    return {c["symbol"]: c.get("sector", "Unknown") for c in config["constituents"]}


def list_available() -> list[str]:
    return sorted(p.stem for p in UNIVERSE_DIR.glob("*.json"))


def list_available_detailed() -> list[dict]:
    results = []
    for p in sorted(UNIVERSE_DIR.glob("*.json")):
        try:
            with open(p) as f:
                c = json.load(f)
            results.append({
                "slug": c.get("slug", p.stem),
                "name": c.get("companyName", p.stem),
                "n_constituents": len(c.get("constituents", [])),
                "file": str(p),
            })
        except Exception:
            results.append({"slug": p.stem, "name": p.stem, "n_constituents": 0, "file": str(p), "error": True})
    return results
