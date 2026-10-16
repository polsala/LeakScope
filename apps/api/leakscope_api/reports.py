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
    native_plot = ""
    native = document.get("native")
    if native:
        root = (
            native["retained_tree"] if native.get("exact_survivors") else native["allocation_tree"]
        )
        rectangles: list[str] = []

        def draw(node, x, width, depth):
            if depth > 20 or len(rectangles) >= 4000 or width < 1:
                return
            label = html.escape(node["name"])
            value = int(node["value"])
            rectangles.append(
                f'<g><title>{label}: {value} observed bytes</title><rect x="{x:.2f}" y="{depth * 22}" width="{max(0, width - 1):.2f}" height="21" fill="hsl({160 + depth * 8},45%,40%)"/></g>'
            )
            cursor = x
            for child in node["children"].values():
                part = width * child["value"] / max(1, value)
                draw(child, cursor, part, depth + 1)
                cursor += part

        draw(root, 0, 800, 0)
        native_plot = (
            (
                "<h2>Observed Python object-block sites</h2><p>Verified current Python frames where available. Exact survivor accounting: "
                if native.get("domain") == "python_block"
                else "<h2>Observed native allocation sites</h2><p>Native stacks only. Exact survivor accounting: "
            )
            + str(bool(native.get("exact_survivors")))
            + '</p><svg viewBox="0 0 800 470" role="img" aria-label="Native allocation flamegraph">'
            + "".join(rectangles)
            + "</svg>"
        )
    python_plot = ""
    if document.get("python_functions"):
        rows = []
        for site in document["python_functions"]["top_sites"][:40]:
            frame = (site.get("frames") or [{}])[0]
            rows.append(
                "<tr><td>"
                + html.escape(str(frame.get("function", "Unknown")))
                + "</td><td>"
                + html.escape(str(frame.get("file", "Unknown")))
                + "</td><td>"
                + html.escape(str(site.get("known_live_bytes")))
                + "</td></tr>"
            )
        python_plot = (
            "<h2>Python context evidence</h2><p>"
            + (
                "Verified allocation-time Python frames in the object-block domain. This does not establish object ownership or full heap coverage."
                if document["python_functions"]["quality"].get("python_exact_allocation_lines")
                else "Temporally correlated function boundaries. Ownership and exact allocation lines are not established."
            )
            + "</p><table><tr><th>Function</th><th>File</th><th>Observed known-live bytes</th></tr>"
            + "".join(rows)
            + "</table>"
        )
    operation_plot = ""
    operations = document.get("operations", {}).get("operations", [])
    if operations:
        operation_rows = []
        for op in operations[:1000]:
            duration = (op["end_ns"] - op["start_ns"]) / 1e6 if op.get("end_ns") else None
            operation_rows.append(
                "<tr><td>"
                + html.escape(op.get("operation", "Unknown"))
                + "</td><td>"
                + html.escape(str(duration))
                + "</td><td>"
                + html.escape(str(op.get("known_live_bytes")))
                + "</td></tr>"
            )
        operation_plot = (
            "<h2>Operation intervals</h2><p>Allocations associated with the most specific completed interval on the same native thread. Temporal association does not establish ownership.</p><table><tr><th>Operation</th><th>Duration (ms)</th><th>Observed surviving bytes</th></tr>"
            + "".join(operation_rows)
            + "</table>"
        )
    payload = html.escape(json.dumps(document, indent=2, ensure_ascii=False))
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:"><title>{title}</title><style>body{{font:16px system-ui;max-width:1000px;margin:48px auto;padding:24px;color:#173038}}h1{{font-size:32px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f0f5f4;padding:24px;border-radius:12px}}svg{{width:100%}}</style><h1>{title}</h1><p>LeakScope · reproducible memory investigation · {html.escape(document.get("version", ""))}</p>{plot}{native_plot}{python_plot}{operation_plot}<p>RSS growth is evidence of process growth; it does not establish an allocation leak.</p><pre>{payload}</pre></html>"""
