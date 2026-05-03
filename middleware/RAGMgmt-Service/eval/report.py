"""Render eval results as a single self-contained HTML report.

The output is one file with no external assets — operators can email it,
attach to a PR, or commit alongside the triples for compliance review.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>RAG Eval Report — Regulated Healthcare Practice Content RAG</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      margin: 0;
      padding: 2rem;
      background: #fafaf6;
      color: #1f2530;
      line-height: 1.4;
    }}
    h1 {{ margin-top: 0; }}
    .summary {{
      background: white;
      padding: 1rem 1.5rem;
      border-radius: 10px;
      margin-bottom: 1.5rem;
      border-left: 4px solid #08434a;
    }}
    .pill {{
      display: inline-block;
      padding: 0.15rem 0.6rem;
      border-radius: 999px;
      font-size: 0.78rem;
      font-weight: 600;
    }}
    .pill-pass {{ background: #dcfce7; color: #166534; }}
    .pill-fail {{ background: #ffe4e6; color: #9f1239; }}
    .pill-warn {{ background: #fef3c7; color: #92400e; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: white;
      border-radius: 10px;
      overflow: hidden;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
    }}
    th, td {{
      padding: 0.6rem 0.8rem;
      text-align: left;
      border-bottom: 1px solid #e2e8f0;
      font-size: 0.88rem;
    }}
    th {{
      background: #08434a;
      color: white;
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    tr:last-child td {{ border-bottom: none; }}
    .topic {{ font-weight: 600; }}
    .num {{ font-variant-numeric: tabular-nums; text-align: right; }}
    .num-fail {{ color: #9f1239; }}
    .num-pass {{ color: #166534; }}
    .meta {{ color: #64748b; font-size: 0.78rem; }}
    .corpora {{ font-family: monospace; font-size: 0.78rem; }}
  </style>
</head>
<body>
  <h1>RAG Eval Report</h1>
  <div class="summary">
    <div class="meta">
      Generated: {generated_at}
      · Triples: {triple_count}
      · Cloud preset: <code>{cloud_preset}</code>
    </div>
    <p>
      <strong>Aggregate scores</strong>:
      faithfulness <span class="num {agg_faith_class}">{agg_faith:.3f}</span>
      · context precision <span class="num {agg_ctx_class}">{agg_ctx:.3f}</span>
      · answer relevance <span class="num {agg_rel_class}">{agg_rel:.3f}</span>
    </p>
    <p>
      <strong>Excel acceptance bars</strong>:
      faithfulness ≥ 0.90 <span class="{agg_faith_pill_class}">{agg_faith_pill}</span>
      · context precision ≥ 0.75 <span class="{agg_ctx_pill_class}">{agg_ctx_pill}</span>
      · answer relevance ≥ 0.85 <span class="{agg_rel_pill_class}">{agg_rel_pill}</span>
    </p>
    <p>
      <strong>Per-triple pass rate</strong>:
      <span class="{all_pass_pill_class}">{all_pass_pill}</span>
      ({triples_all_pass} / {triple_count} triples passed all 3 thresholds)
    </p>
  </div>
  <table>
    <thead>
      <tr>
        <th>ID</th>
        <th>Topic</th>
        <th>Corpora</th>
        <th class="num">Faith</th>
        <th class="num">Ctx-prec</th>
        <th class="num">Ans-rel</th>
        <th>Verdict</th>
      </tr>
    </thead>
    <tbody>
{rows}
    </tbody>
  </table>
</body>
</html>
"""


_ROW_TEMPLATE = (
    "      <tr>"
    "<td class=\"meta\">{id}</td>"
    "<td class=\"topic\">{topic}</td>"
    "<td class=\"corpora\">{corpora}</td>"
    "<td class=\"num {faith_class}\">{faith:.3f}</td>"
    "<td class=\"num {ctx_class}\">{ctx:.3f}</td>"
    "<td class=\"num {rel_class}\">{rel:.3f}</td>"
    "<td><span class=\"{verdict_class}\">{verdict}</span></td>"
    "</tr>"
)


def _pass_class(value: float, threshold: float) -> str:
    return "num-pass" if value >= threshold else "num-fail"


def _pass_pill(value: float, threshold: float) -> tuple[str, str]:
    if value >= threshold:
        return "pill pill-pass", "PASS"
    return "pill pill-fail", "FAIL"


def render_report(
    *,
    cloud_preset: str,
    rows: list[dict],
) -> str:
    """`rows` is a list of per-triple result dicts with keys:
        id, topic, corpora_present, faithfulness, context_precision,
        answer_relevance, all_pass.
    """
    if not rows:
        raise ValueError("render_report requires at least one row")

    n = len(rows)
    agg_faith = sum(r["faithfulness"] for r in rows) / n
    agg_ctx = sum(r["context_precision"] for r in rows) / n
    agg_rel = sum(r["answer_relevance"] for r in rows) / n
    triples_all_pass = sum(1 for r in rows if r["all_pass"])

    agg_faith_pill_class, agg_faith_pill = _pass_pill(agg_faith, 0.90)
    agg_ctx_pill_class,   agg_ctx_pill   = _pass_pill(agg_ctx, 0.75)
    agg_rel_pill_class,   agg_rel_pill   = _pass_pill(agg_rel, 0.85)

    if triples_all_pass == n:
        all_pass_pill_class, all_pass_pill = "pill pill-pass", "ALL PASS"
    elif triples_all_pass == 0:
        all_pass_pill_class, all_pass_pill = "pill pill-fail", "ALL FAIL"
    else:
        all_pass_pill_class, all_pass_pill = "pill pill-warn", "MIXED"

    rendered_rows: list[str] = []
    for r in rows:
        verdict_class, verdict = ("pill pill-pass", "PASS") if r["all_pass"] else ("pill pill-fail", "FAIL")
        rendered_rows.append(
            _ROW_TEMPLATE.format(
                id=html.escape(r["id"]),
                topic=html.escape(r["topic"]),
                corpora=html.escape(",".join(r.get("corpora_present") or [])),
                faith=r["faithfulness"],
                ctx=r["context_precision"],
                rel=r["answer_relevance"],
                faith_class=_pass_class(r["faithfulness"], 0.90),
                ctx_class=_pass_class(r["context_precision"], 0.75),
                rel_class=_pass_class(r["answer_relevance"], 0.85),
                verdict_class=verdict_class,
                verdict=verdict,
            )
        )

    return _HTML_TEMPLATE.format(
        generated_at=datetime.now(timezone.utc).isoformat(),
        triple_count=n,
        cloud_preset=html.escape(cloud_preset),
        agg_faith=agg_faith,
        agg_ctx=agg_ctx,
        agg_rel=agg_rel,
        agg_faith_class=_pass_class(agg_faith, 0.90),
        agg_ctx_class=_pass_class(agg_ctx, 0.75),
        agg_rel_class=_pass_class(agg_rel, 0.85),
        agg_faith_pill_class=agg_faith_pill_class,
        agg_faith_pill=agg_faith_pill,
        agg_ctx_pill_class=agg_ctx_pill_class,
        agg_ctx_pill=agg_ctx_pill,
        agg_rel_pill_class=agg_rel_pill_class,
        agg_rel_pill=agg_rel_pill,
        triples_all_pass=triples_all_pass,
        all_pass_pill_class=all_pass_pill_class,
        all_pass_pill=all_pass_pill,
        rows="\n".join(rendered_rows),
    )
