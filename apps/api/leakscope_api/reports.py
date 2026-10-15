import html
import json


def render(document: dict) -> str:
    title = html.escape(document["title"])
    samples = document.get("timeline", [])
    plot = ""
    if samples:
        ys = [s["rss"] for s in samples]
        lo, hi = min(ys), max(ys)
        coords = " ".join(
            f"{20 + i * 760 / max(1, len(ys) - 1):.2f},{180 - (y - lo) * 150 / max(1, hi - lo):.2f}"
            for i, y in enumerate(ys)
        )
        plot = f'<svg viewBox="0 0 800 210" role="img" aria-label="RSS timeline"><polyline points="{coords}" fill="none" stroke="#0d9488" stroke-width="3"/></svg>'
    payload = html.escape(json.dumps(document, indent=2, ensure_ascii=False))
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:"><title>{title}</title><style>body{{font:16px system-ui;max-width:1000px;margin:48px auto;padding:24px;color:#173038}}h1{{font-size:32px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f0f5f4;padding:24px;border-radius:12px}}svg{{width:100%}}</style><h1>{title}</h1><p>LeakScope · reproducible memory investigation · {html.escape(document.get("version", ""))}</p>{plot}<p>RSS growth is evidence of process growth; it does not establish an allocation leak.</p><pre>{payload}</pre></html>"""
