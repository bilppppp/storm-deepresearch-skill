# Evaluation Checklist

Score each item 0/1/2.

## Source grounding
- Important claims are cited.
- Citations support the exact claims.
- Contested claims include both sides.
- Current claims include retrieval dates.

## Research quality
- Perspectives are adapted to the topic.
- Contradictions are explicit.
- Blind spots are identified.
- Confidence is ranked realistically.

## Report quality
- Executive summary is useful to the target audience.
- Full Chinese dossiers contain 8000-10000 evidence-led body characters unless the brief explicitly requests a shorter mode.
- Every answered STORM question and material claim is consumed by the report outline.
- Added length comes from mechanisms, evidence, counterevidence, examples, implications, and limits rather than repetition.
- Findings are actionable and caveated.
- Limitations are honest.
- Writing is polished and coherent.

## Export quality
- Markdown exists.
- HTML is readable and print-friendly.
- PDF exists or limitation is documented.
- No local paths leak.

## Output safety
- New runs default below the user workspace output root.
- Existing run directories are never reinitialized.
- Symlink resolution cannot redirect writes outside the approved root or package.
- Source and Claim ledgers preserve existing IDs and records across updates.
