"""Build the YouTube presentation deck for Project A — Excel-driven walkthrough.

Run from the repo root:

    python3 docs/Presentation/build_pptx.py

Outputs: docs/Presentation/01-RAG-Introduction-ProjectA.pptx

The deck mirrors the 1_Project_A_Healthcare_Content worksheet section by
section: objective → datasets → design patterns → AWS architecture →
project architecture → patterns in action → demo → scorecard.

Each slide carries:
  * Title
  * Bullet points (kept short for YouTube readability)
  * Speaker notes (the script in the Notes pane — drives the voiceover)

Re-running the script overwrites the .pptx — keep your edits in this script,
not in PowerPoint, so the deck stays reproducible.
"""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches, Pt


OUTPUT_PATH = Path(__file__).resolve().parent / "01-RAG-Introduction-ProjectA.pptx"

# Brand palette mirrors docs/Design/architecture-diagrams.drawio + the customer
# portal styles. Deep teal for regulator/title, cyan for evidence, amber for
# voice. Off-white background for slide chrome readability.
COLOR_TITLE_BG = RGBColor(0x08, 0x43, 0x4A)        # deep teal
COLOR_TITLE_FG = RGBColor(0xFF, 0xFF, 0xFF)
COLOR_BODY_BG = RGBColor(0xFA, 0xFA, 0xF6)         # warm off-white
COLOR_BODY_FG = RGBColor(0x1F, 0x25, 0x30)         # deep slate
COLOR_ACCENT = RGBColor(0xF0, 0xB0, 0x4A)          # warm amber
COLOR_REGULATOR = RGBColor(0x08, 0x43, 0x4A)
COLOR_EVIDENCE = RGBColor(0x00, 0x89, 0xA7)
COLOR_VOICE = RGBColor(0xF0, 0xB0, 0x4A)

SLIDE_WIDTH = Inches(13.333)   # 16:9
SLIDE_HEIGHT = Inches(7.5)


def _set_slide_background(slide, rgb):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = rgb


def _add_text_box(slide, *, left, top, width, height, text, font_size=18,
                  bold=False, color=None, align_left=True):
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = text
    run.font.size = Pt(font_size)
    run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color
    if not align_left:
        from pptx.enum.text import PP_ALIGN
        p.alignment = PP_ALIGN.CENTER
    return box


def _add_bullets(slide, *, left, top, width, height, items, font_size=20,
                 color=None, bullet_char="•"):
    """Render a vertical list of bullet items as a textbox. Each item is a
    string OR a dict {text, bold, indent} for richer formatting."""
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    color = color or COLOR_BODY_FG
    for idx, item in enumerate(items):
        if isinstance(item, str):
            text = item
            bold = False
            indent = 0
        else:
            text = item.get("text", "")
            bold = item.get("bold", False)
            indent = item.get("indent", 0)
        if idx == 0:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()
        prefix = ("  " * indent) + (f"{bullet_char} " if bullet_char else "")
        run = p.add_run()
        run.text = prefix + text
        run.font.size = Pt(font_size)
        run.font.bold = bold
        run.font.color.rgb = color
    return box


def _add_table(slide, *, left, top, width, height, rows):
    """rows[0] is the header row. Returns the table shape."""
    n_rows = len(rows)
    n_cols = max(len(r) for r in rows)
    shape = slide.shapes.add_table(n_rows, n_cols, left, top, width, height)
    table = shape.table
    for r_idx, row in enumerate(rows):
        for c_idx in range(n_cols):
            cell = table.cell(r_idx, c_idx)
            value = row[c_idx] if c_idx < len(row) else ""
            cell.text = ""  # clear default
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            run = p.add_run()
            run.text = str(value)
            run.font.size = Pt(13 if r_idx > 0 else 14)
            run.font.bold = (r_idx == 0)
            if r_idx == 0:
                cell.fill.solid()
                cell.fill.fore_color.rgb = COLOR_TITLE_BG
                run.font.color.rgb = COLOR_TITLE_FG
            else:
                run.font.color.rgb = COLOR_BODY_FG
    return shape


def _add_speaker_notes(slide, notes_text):
    notes_slide = slide.notes_slide
    notes_tf = notes_slide.notes_text_frame
    notes_tf.text = notes_text


def _add_visual_hint(slide, text):
    """Bottom-of-slide inline reminder of what visual to drop in."""
    box = slide.shapes.add_textbox(
        Inches(0.5), Inches(6.85), Inches(12.3), Inches(0.5)
    )
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = f"🖼  Visual: {text}"
    run.font.size = Pt(11)
    run.font.italic = True
    run.font.color.rgb = RGBColor(0x88, 0x88, 0x88)


def _add_title_bar(slide, title, subtitle=None):
    # Title strip across the top in deep teal.
    bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, 0, 0, SLIDE_WIDTH, Inches(1.0)
    )
    bar.fill.solid()
    bar.fill.fore_color.rgb = COLOR_TITLE_BG
    bar.line.fill.background()
    tf = bar.text_frame
    tf.margin_left = Inches(0.5)
    tf.margin_top = Inches(0.15)
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = title
    run.font.size = Pt(28)
    run.font.bold = True
    run.font.color.rgb = COLOR_TITLE_FG
    if subtitle:
        p2 = tf.add_paragraph()
        run2 = p2.add_run()
        run2.text = subtitle
        run2.font.size = Pt(14)
        run2.font.color.rgb = COLOR_ACCENT


# ---------------------------------------------------------------------------
# Slides
# ---------------------------------------------------------------------------

def _build_slide_1_title(prs):
    """Series + episode title slide."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank layout
    _set_slide_background(slide, COLOR_TITLE_BG)

    _add_text_box(
        slide, left=Inches(0.8), top=Inches(2.0),
        width=Inches(11.7), height=Inches(1.0),
        text="RAG Mastery — Episode 1", font_size=32, bold=True,
        color=COLOR_ACCENT,
    )
    _add_text_box(
        slide, left=Inches(0.8), top=Inches(2.9),
        width=Inches(11.7), height=Inches(1.5),
        text="Regulated Healthcare Practice Content RAG",
        font_size=46, bold=True, color=COLOR_TITLE_FG,
    )
    _add_text_box(
        slide, left=Inches(0.8), top=Inches(4.5),
        width=Inches(11.7), height=Inches(1.0),
        text="A compliance-first RAG stack — every claim must map to a citable source.",
        font_size=20, color=COLOR_TITLE_FG,
    )
    _add_text_box(
        slide, left=Inches(0.8), top=Inches(6.5),
        width=Inches(11.7), height=Inches(0.5),
        text="github.com/javakishore-veleti/Regulated-Healthcare-Practice-Content-RAG",
        font_size=14, color=COLOR_ACCENT,
    )
    _add_speaker_notes(slide, (
        "Welcome to RAG Mastery, Episode 1. We're walking through Project A from "
        "the RAG_Mastery_Projects.xlsx worksheet — a compliance-first RAG stack "
        "for allied-health practices in regulated jurisdictions. "
        "In the next 15 minutes we'll cover what the worksheet asks for, the four "
        "RAG patterns it names, the AWS architecture it specifies, and a live demo "
        "of all of it running. The repo link is on screen — pause it now if you "
        "want to clone alongside."
    ))


def _build_slide_2_objective(prs):
    """Slide 1 of the body — Objective from the worksheet."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _set_slide_background(slide, COLOR_BODY_BG)
    _add_title_bar(
        slide,
        "Objective",
        "From the worksheet — \"About this project\"",
    )

    bullets = [
        {"text": "Business problem", "bold": True},
        {"text": "Allied-health practices in regulated jurisdictions need SEO content that complies with rules forbidding testimonials, misleading therapeutic claims, and unverified efficacy.", "indent": 1},
        {"text": "RAG goal", "bold": True},
        {"text": "Ground every draft in three corpora: regulator's published advertising rules · practice's own voice corpus · open-access clinical evidence.", "indent": 1},
        {"text": "Why RAG", "bold": True},
        {"text": "A plain LLM produces a regulatory breach in the first paragraph. RAG forces every claim to map to a retrievable, citable source — with a guardrail layer for banned phrases.", "indent": 1},
    ]
    _add_bullets(
        slide, left=Inches(0.6), top=Inches(1.4),
        width=Inches(12.1), height=Inches(5.3),
        items=bullets, font_size=18, bullet_char="",
    )
    _add_visual_hint(slide, "Excel screenshot of the 'About this project' rows")
    _add_speaker_notes(slide, (
        "The Project A worksheet states the problem precisely. Allied-health practices "
        "in regulated jurisdictions need marketing content that respects AHPRA in "
        "Australia, FTC in the US, and so on — rules that forbid testimonials, "
        "misleading claims, and unverified efficacy statements. The worksheet's RAG "
        "goal is explicit: ground every draft in three corpora — the regulator's "
        "rules, the practice's voice, and clinical evidence. The 'why RAG' is the "
        "line you should remember: a plain LLM produces a regulatory breach in the "
        "first paragraph. RAG forces every claim to a citable source. That's the door."
    ))


def _build_slide_3_datasets(prs):
    """Datasets section."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _set_slide_background(slide, COLOR_BODY_BG)
    _add_title_bar(
        slide,
        "Datasets",
        "From the worksheet — \"Datasets\" section, ≥ 10 GB combined",
    )

    rows = [
        ["Dataset", "Size", "Role in the three-corpora model"],
        ["Public regulator guidelines (AHPRA AU, FTC US, GMC UK)",
         "~50–100 MB", "Regulator corpus"],
        ["ncbi/pubmed (HuggingFace) — MeSH-filtered (MSK / chronic-pain)",
         "~25 GB → 6 GB filtered", "Clinical evidence corpus"],
        ["PMC Open Access Subset",
         "~50 GB → 5 GB sample", "Clinical evidence (full-text)"],
        ["Kaggle: medicaltranscriptions (tboyle10)",
         "~1 GB", "De-id practice / synthetic notes"],
        ["Common Crawl (allied-health domains, filtered)",
         "~3 GB", "Practice-voice / tone corpus"],
    ]
    _add_table(
        slide, left=Inches(0.5), top=Inches(1.4),
        width=Inches(12.3), height=Inches(4.5),
        rows=rows,
    )
    _add_visual_hint(slide, "Excel screenshot of the Datasets table")
    _add_speaker_notes(slide, (
        "Five datasets, ten gigabytes plus. Three groups: regulator rules from "
        "AHPRA, FTC, GMC for the compliance side. PubMed and PMC Open Access for "
        "clinical evidence — filtered by MeSH terms for musculoskeletal scope. "
        "Kaggle medical transcriptions for de-identification practice. Common "
        "Crawl filtered to allied-health domains for tone analysis. These are "
        "exactly what the worksheet's Datasets section names — and they slot "
        "one-to-one into the three-corpora grounding model the worksheet wants. "
        "We'll see them flow through retrieval in a minute."
    ))


def _build_slide_4_design_patterns(prs):
    """Four named design patterns."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _set_slide_background(slide, COLOR_BODY_BG)
    _add_title_bar(
        slide,
        "Design patterns",
        "From the worksheet — \"Patterns from SKILL.md\" row",
    )

    # 2x2 grid of pattern cards
    card_w, card_h = Inches(6.0), Inches(2.5)
    gap = Inches(0.3)
    start_x, start_y = Inches(0.5), Inches(1.4)

    cards = [
        ("1. Hybrid search + cross-encoder rerank",
         "BM25 + dense, fused with RRF, reranked. Tackles the 'recall good, precision bad' failure mode.",
         COLOR_REGULATOR),
        ("2. Parent-child chunking",
         "Children for retrieval recall; parents for drafter context. Markdown-aware → section anchors.",
         COLOR_EVIDENCE),
        ("3. Self-RAG faithfulness loop",
         "Score every sentence vs. retrieved citations. Below threshold → regenerate with a hint.",
         COLOR_VOICE),
        ("4. Output guardrails",
         "Banned-phrase / forbidden-claim regex on the final output. AHPRA-aligned, layered with Bedrock in prod.",
         RGBColor(0x9F, 0x12, 0x39)),
    ]

    for idx, (title, desc, color) in enumerate(cards):
        row, col = divmod(idx, 2)
        x = start_x + col * (card_w + gap)
        y = start_y + row * (card_h + Inches(0.3))
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, card_w, card_h)
        card.fill.solid()
        card.fill.fore_color.rgb = COLOR_BODY_BG
        card.line.color.rgb = color
        card.line.width = Pt(2.5)
        card.shadow.inherit = False

        tf = card.text_frame
        tf.margin_left = Inches(0.25)
        tf.margin_right = Inches(0.25)
        tf.margin_top = Inches(0.2)
        tf.word_wrap = True
        p1 = tf.paragraphs[0]
        r1 = p1.add_run()
        r1.text = title
        r1.font.size = Pt(20)
        r1.font.bold = True
        r1.font.color.rgb = color
        p2 = tf.add_paragraph()
        p2.space_before = Pt(8)
        r2 = p2.add_run()
        r2.text = desc
        r2.font.size = Pt(14)
        r2.font.color.rgb = COLOR_BODY_FG

    _add_speaker_notes(slide, (
        "These are the four named patterns straight from the worksheet's "
        "'Patterns from SKILL.md' row. Each one solves a specific RAG failure mode. "
        "Hybrid plus rerank fixes 'recall is good but precision is bad.' Parent-child "
        "chunking fixes 'children are small enough to retrieve but too small to "
        "reason over.' Self-RAG fixes 'the LLM said something the citations don't "
        "actually support.' Output guardrails catch the things that slip past "
        "everything else. The rest of the talk is about how each one is implemented "
        "in the project — but the worksheet picked these four for a reason. They're "
        "orthogonal. You need all four for compliance-grade RAG."
    ))


def _build_slide_5_aws_architecture(prs):
    """AWS architecture section."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _set_slide_background(slide, COLOR_BODY_BG)
    _add_title_bar(
        slide,
        "AWS architecture",
        "From the worksheet — \"AWS architecture\" section",
    )

    rows = [
        ["Layer", "AWS service named in the worksheet"],
        ["Ingestion", "S3 → AWS Glue → Amazon Textract → Comprehend Medical → Lambda"],
        ["Embedding", "Amazon Bedrock — Titan Embeddings v2 OR Cohere Embed v4"],
        ["Vector store", "Amazon OpenSearch Serverless (hybrid k-NN + BM25)"],
        ["Retrieval", "Bedrock Knowledge Bases + Bedrock Rerank"],
        ["Generation", "Bedrock Claude Opus 4.7 (drafting) + Claude Haiku 4.5 (compliance)"],
        ["Guardrails", "Amazon Bedrock Guardrails — denied topics + PII filter"],
        ["Orchestration", "Step Functions + Lambda; or Bedrock Agents"],
        ["Observability", "OTel ADOT → Langfuse on ECS Fargate; CloudWatch for infra"],
    ]
    _add_table(
        slide, left=Inches(0.5), top=Inches(1.4),
        width=Inches(12.3), height=Inches(5.4),
        rows=rows,
    )
    _add_visual_hint(slide, "Excel screenshot of the AWS architecture table")
    _add_speaker_notes(slide, (
        "The worksheet doesn't just say 'deploy to AWS' — it names every service "
        "per layer. Bedrock for embedding AND drafting AND guardrails. OpenSearch "
        "Serverless for hybrid retrieval. Step Functions for orchestration. Langfuse "
        "self-hosted on ECS for traces. Every cell in this table maps to a "
        "switchable backend in the implementation. You flip one env flag — "
        "RAG_RETRIEVAL_BACKEND=aws_opensearch_serverless — and the same code path "
        "now talks to AOSS instead of pgvector. Same for the embedder, the drafter, "
        "the guardrails. That's why the factory pattern in the implementation "
        "matters: the worksheet's architecture row IS the production deploy."
    ))


def _build_slide_6_project_architecture(prs):
    """One slide on this project's actual architecture."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _set_slide_background(slide, COLOR_BODY_BG)
    _add_title_bar(
        slide,
        "How the project actually runs",
        "One architecture slide — full diagram in docs/Design/",
    )

    bullets = [
        "Two FastAPI services: DataMgmt (catalog, ingest) + RAGMgmt (chunk, retrieve, generate)",
        "Postgres + pgvector locally → flips to OpenSearch Serverless in AWS via one env var",
        "Airflow DAG for fetch → chunk → embed (markdown-aware, attaches section anchors)",
        "Two Angular portals: admin (curators) + customer (content authors), both path-routed /api/*",
        "Every load-bearing component is a factory — local-dev defaults, production deps as opt-in extras",
        "Same code path runs unchanged on AWS EKS, Azure AKS, GCP GKE, or any container target",
    ]
    _add_bullets(
        slide, left=Inches(0.6), top=Inches(1.4),
        width=Inches(12.1), height=Inches(5.3),
        items=bullets, font_size=18,
    )
    _add_visual_hint(
        slide,
        "docs/Design/architecture-diagrams.drawio — Tab 1 (System Local Dev). Don't dwell.",
    )
    _add_speaker_notes(slide, (
        "One slide on the project's architecture so you have context for the demo. "
        "Two FastAPI services. Postgres with pgvector for local dev — same code "
        "talks to OpenSearch Serverless in production. Airflow DAG for ingest. Two "
        "Angular portals on top. The thing that makes the worksheet's 'flip to AWS' "
        "promise real is the factory pattern — every load-bearing piece, drafter, "
        "embedder, reranker, retrieval, guardrails — has a factory that picks the "
        "implementation per env var. Local dev is zero-deps. Production is one pip "
        "extra and one env flag away. Now let's see the four patterns running."
    ))


def _build_slide_7_patterns_in_action(prs):
    """The four RAG patterns in action — combined view."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _set_slide_background(slide, COLOR_BODY_BG)
    _add_title_bar(
        slide,
        "The four patterns in action",
        "How each Excel-named pattern is implemented in this project",
    )

    rows = [
        ["Pattern", "Implementation in this project"],
        ["Hybrid + Rerank",
         "RRF fuses BM25 (Postgres tsvector) + dense (pgvector cosine). "
         "TokenOverlap default; CrossEncoder via [cross-encoder-rerank] extra. "
         "Three-corpora variant runs the pipeline once per corpus → guaranteed mix."],
        ["Parent-child chunking",
         "Children ~256 chars, parents ~1500 chars. Markdown-aware: '## Heading' lines "
         "tag every parent with parent_heading + section_id. Citations cite by "
         "[Public_Regulator_Guidelines#Testimonials], not opaque [1]."],
        ["Self-RAG loop",
         "Token-overlap scorer per sentence vs. retrieved citations. Below threshold "
         "→ drafter receives a hint listing unsupported sentences and rewrites. "
         "Capped retries; deterministic stub drafter short-circuits the loop."],
        ["Output guardrails",
         "30-rule AHPRA YAML policy with rule_id + severity + char offsets. Layered "
         "mode (regex first → Bedrock Guardrails) is the recommended production "
         "posture; Bedrock catches paraphrased violations the regex misses."],
    ]
    _add_table(
        slide, left=Inches(0.5), top=Inches(1.4),
        width=Inches(12.3), height=Inches(5.0),
        rows=rows,
    )
    _add_speaker_notes(slide, (
        "All four patterns on one slide because they fit together. Hybrid plus "
        "rerank — BM25 from Postgres tsvector plus dense from pgvector, fused with "
        "RRF, then reranked. The three-corpora trick is the project's own "
        "contribution: instead of letting whichever corpus dominates a single "
        "ranking, the pipeline runs once per corpus so the drafter sees a balanced "
        "mix from regulator, voice, and evidence. Parent-child chunking is "
        "markdown-aware — headings become section anchors so citations look like "
        "Dataset#Section, not opaque [1]. Self-RAG: every sentence scored, "
        "hint-driven regenerate when ungrounded. Guardrails: 30 AHPRA rules in YAML, "
        "layered with Bedrock for semantic catches. Together — that's the "
        "compliance-grade RAG the worksheet is asking for."
    ))


def _build_slide_8_demo(prs):
    """Demo slide — pre-recorded MP4 placeholder."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _set_slide_background(slide, COLOR_BODY_BG)
    _add_title_bar(
        slide,
        "Demo: full pipeline in 90 seconds",
        "Topic → three corpora → cited draft → faithfulness + guardrails verdicts",
    )

    bullets = [
        "Topic: \"What does AHPRA say about testimonials in advertising?\"",
        "Three-corpora coverage panel: regulator + voice present, evidence missing for this regulatory question",
        "Per-citation chips colored by corpus type — deep teal regulator, amber voice",
        "Faithfulness pill: \"score 92% · passed\" + Guardrails pill: \"0 violations · passed\"",
        "Switch drafter → faithfulness drops below threshold → regenerate loop kicks in visibly",
    ]
    _add_bullets(
        slide, left=Inches(0.6), top=Inches(1.4),
        width=Inches(12.1), height=Inches(5.3),
        items=bullets, font_size=18,
    )
    _add_visual_hint(
        slide,
        "Pre-recorded MP4 (~75 s) of the customer portal Generate flow. Cut tight, "
        "no narration over the recording — your live voice carries.",
    )
    _add_speaker_notes(slide, (
        "Pre-recorded demo, ninety seconds. Regulator-shaped topic. Hit Generate. "
        "The coverage panel at the top tells me regulator and practice voice "
        "contributed; clinical evidence is missing because this is a regulatory "
        "question, not a clinical one. Each citation has a chip — deep teal for "
        "regulator, amber for voice. Faithfulness pill says 92 percent of sentences "
        "supported. Guardrails pill says zero violations. If I switch to a more "
        "aggressive drafter, faithfulness drops, the regenerate loop kicks in, and "
        "the JSON sidebar shows the hint Claude received before rewriting. All four "
        "patterns visible in one screen."
    ))


def _build_slide_9_close(prs):
    """Hands-on tasks scorecard + CTA."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _set_slide_background(slide, COLOR_BODY_BG)
    _add_title_bar(
        slide,
        "What's done — and where the repo lives",
        "Worksheet \"Hands-on tasks\" scorecard",
    )

    bullets = [
        "12 of the 14 in-scope worksheet tasks done (3 are operator-infra, out of code scope)",
        "Eval harness writes an HTML report against the worksheet's bars: faithfulness ≥ 0.9, ctx-prec ≥ 0.75, ans-rel ≥ 0.85",
        "146 tests, stdlib only, ~0.2 s in CI",
        "7 operator how-to docs in docs/operator-howto/ — Bedrock, AOSS, cross-encoder, real embedder, Langfuse, eval, new-dataset",
        "6-tab architecture diagrams in docs/Design/",
    ]
    _add_bullets(
        slide, left=Inches(0.6), top=Inches(1.4),
        width=Inches(12.1), height=Inches(4.0),
        items=bullets, font_size=18,
    )

    # CTA strip at the bottom
    cta = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        Inches(0.5), Inches(5.6), Inches(12.3), Inches(1.3),
    )
    cta.fill.solid()
    cta.fill.fore_color.rgb = COLOR_TITLE_BG
    cta.line.fill.background()
    cta_tf = cta.text_frame
    cta_tf.margin_left = Inches(0.4)
    cta_tf.margin_top = Inches(0.2)
    p = cta_tf.paragraphs[0]
    r = p.add_run()
    r.text = "⭐  Star the repo"
    r.font.size = Pt(20)
    r.font.bold = True
    r.font.color.rgb = COLOR_ACCENT
    p2 = cta_tf.add_paragraph()
    p2.space_before = Pt(6)
    r2 = p2.add_run()
    r2.text = "github.com/javakishore-veleti/Regulated-Healthcare-Practice-Content-RAG"
    r2.font.size = Pt(18)
    r2.font.color.rgb = COLOR_TITLE_FG
    p3 = cta_tf.add_paragraph()
    p3.space_before = Pt(4)
    r3 = p3.add_run()
    r3.text = "Next episode: Project B in the RAG Mastery series"
    r3.font.size = Pt(14)
    r3.font.italic = True
    r3.font.color.rgb = COLOR_TITLE_FG

    _add_speaker_notes(slide, (
        "Final slide. The worksheet's Hands-on tasks section lists seventeen items. "
        "Twelve of the fourteen in-scope ones are implemented; the remaining three "
        "are pure operator infrastructure that's out of the RAG-functionality scope "
        "of this episode. The eval harness scores against the worksheet's own "
        "acceptance bars and writes an HTML report. Repo's linked below. Star it if "
        "it helped. Next episode tackles Project B in the series. Thanks for watching."
    ))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    prs = Presentation()
    prs.slide_width = SLIDE_WIDTH
    prs.slide_height = SLIDE_HEIGHT

    _build_slide_1_title(prs)
    _build_slide_2_objective(prs)
    _build_slide_3_datasets(prs)
    _build_slide_4_design_patterns(prs)
    _build_slide_5_aws_architecture(prs)
    _build_slide_6_project_architecture(prs)
    _build_slide_7_patterns_in_action(prs)
    _build_slide_8_demo(prs)
    _build_slide_9_close(prs)

    prs.save(OUTPUT_PATH)
    print(f"Wrote {OUTPUT_PATH}  ({len(prs.slides)} slides)")


if __name__ == "__main__":
    main()
