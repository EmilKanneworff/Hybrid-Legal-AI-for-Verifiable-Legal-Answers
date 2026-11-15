# LLM judge runs

This folder holds the three runs of the blind LLM judge that Chapter 6 and Appendix E of the thesis report.

- **Judge.** Claude Sonnet 5.5 (`claude-sonnet-5-5`), run three times on the 70 answers that the legal reviewer assessed, which gives 2,100 decisions. The judge did not see the legal reviewer's labels.
- **Prompt and criteria.** `Evaluation/prompts/llm_judge_prompt_v3_c04_reviewer_wording.txt` and `Evaluation/scoring/TEN_CRITERIA_JUDGE_RUBRIC_V5_C04_ALIGNED.md`. C04 is worded exactly as in the legal reviewer's review tool ("material statements are attributed to an identifiable source"), so both assessors apply the same ten criteria.
- **Fingerprints.** `prompt_hash` in `ai_review_c04_aligned.csv` can be recomputed from the files in this repository for all 210 assessments. Each assessment records `judged_at` and `attempts`.

## Files

- `ai_review_c04_aligned.csv`: 210 judge assessments (70 answers × runs 1–3), with labels and reasons.
- `raw/`: the raw provider response for every assessment.
- `results/table3_agreement.csv` and `results/table4_stability.csv`: the review tool's agreement and stability tables (all 70 answers).
- `results/judge_agreement_subsets.csv`: agreement, Cohen's κ, stability and direction for the 56 answers without source and with correct source, and for the 14 answers from my own RAG system.

## Reproduce

```
Evaluation/.venv/bin/python -m Evaluation.scripts.run_llm_judge_c04_aligned --repeat 1   # and 2, 3
python3 Evaluation/scripts/agreement_report_v5.py Evaluation/outputs/v5_judge_c04_aligned/ai_review_c04_aligned.csv --csv OUT.csv
python3 Evaluation/scripts/check_thesis_numbers.py
```
