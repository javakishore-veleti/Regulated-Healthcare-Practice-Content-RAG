# YouTube presentation deck

Source-controlled deck for the RAG Mastery Episode 1 walkthrough of Project A.

## Files

| File | What |
|---|---|
| `01-RAG-Introduction-ProjectA.pptx` | The 9-slide deck (16:9, 15-minute pacing). Open in PowerPoint / Keynote / LibreOffice Impress. |
| `build_pptx.py` | The python-pptx script that builds the .pptx. **Source of truth — keep edits here, not in the .pptx**, so the deck stays reproducible. |

## Why python-pptx instead of editing the .pptx directly

Slide content drifts. Speaker notes get rewritten. Bullet wording gets tuned per take. Keeping all of that in a script means:

- Diffs are reviewable in PRs (line-oriented, not binary blob).
- Re-running `python3 docs/Presentation/build_pptx.py` regenerates the deck from scratch.
- Speaker notes stay aligned with bullet points (no "I edited the slide but forgot to update the script" drift).

## Re-building

```sh
python3 docs/Presentation/build_pptx.py
# → wrote docs/Presentation/01-RAG-Introduction-ProjectA.pptx (9 slides)
```

Requires `python-pptx` (already in the repo's Python venv: `pip install python-pptx`).

## Slide structure

Mirrors the `1_Project_A_Healthcare_Content` worksheet's section order:

| # | Slide | Excel section it maps to |
|---|---|---|
| 1 | Title — RAG Mastery Episode 1 | (intro) |
| 2 | Objective | "About this project" — Business problem + RAG goal + Why RAG |
| 3 | Datasets | "Datasets" section |
| 4 | Design patterns | "Patterns from SKILL.md" row |
| 5 | AWS architecture | "AWS architecture" section |
| 6 | How the project actually runs | (one architecture slide for context) |
| 7 | The four patterns in action | (implementation per pattern) |
| 8 | Demo | (pre-recorded MP4 placeholder) |
| 9 | What's done + repo CTA | "Hands-on tasks" section |

## Speaker notes

Every slide carries a verbatim voice-over script in the Notes pane (~60–110 seconds at 150 wpm). When you press Play in PowerPoint with the Presenter view on, the script reads naturally as the slide is displayed.

To export a script-only PDF for prompter use:

```sh
# In PowerPoint: File → Export → Notes Pages → PDF
```

## Visual placeholders

Some slides have a small italic "🖼  Visual: …" line at the bottom — these are reminders of what to drop in (Excel screenshots, drawio tab exports, demo MP4). Replace with the actual asset before recording.

Recommended sources:

- Excel screenshots → crop directly from `RAG_Mastery_Projects.xlsx → 1_Project_A_Healthcare_Content`.
- Architecture diagrams → export each tab from `docs/Design/architecture-diagrams.drawio` as PNG.
- Demo recording → screen-capture the customer portal at http://localhost:4300 against a live stack.

## Pacing reference

| Block | Slides | Duration |
|---|---|---:|
| Title | 1 | 0:30 |
| Objective + Datasets + Patterns + AWS | 2–5 | 7:00 |
| Project architecture | 6 | 1:30 |
| Patterns in action | 7 | 3:00 |
| Demo | 8 | 2:30 |
| Close | 9 | 0:30 |
| **Total** | **9** | **15:00** |
