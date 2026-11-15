# Versioned Official SU Sources

> **Agent Metadata**
> - **Document type:** Evaluation source manifest.
> - **Thesis role:** Records the official sources frozen for temporal and citation control in the XHAILe-derived SU evaluation.
> - **Use when:** Regenerating testcases, checking legal-source dates or documenting benchmark reproducibility.
> - **Do not use for:** Treating a technical status check as independent legal-expert validation.
> - **Key concepts:** Retsinformation, temporal validity, SU-loven, SU-bekendtgoerelsen, handicaptillaeg guidance.
> - **Source basis:** Official XML downloaded from Retsinformation on 2026-10-16.
> - **Evidence status:** Preserved primary-source copies used by the evaluation generator and validator.
> - **Read depth:** Read fully before replacing or refreshing any source file.
> - **Related files:** `../legal_authorities_su_v1.json`, `../testcases_su_guidance_qa_v4.jsonl`, `../expert_answer_criteria_su_guidance_qa_v4.csv`, `../../scripts/prepare_source_grounding_testcases.py`.
> - **Last updated:** 2026-10-22.

## Active Sources

| Local file | Official document | Role |
|---|---|---|
| `raw/VEJ_10157_2026_handicaptillaeg.xml` | [VEJ nr. 10157 af 05/10/2026](https://www.retsinformation.dk/eli/retsinfo/2026/10157) | Current guidance and active answer passages. |
| `raw/BEK_841_2026_SU_bekendtgoerelsen.xml` | [BEK nr. 841 af 28/09/2026](https://www.retsinformation.dk/eli/lta/2026/841) | Current regulation; effective 1 October 2026 and repeals BEK nr. 794/2025. |
| `raw/LBK_395_2023_SU_loven.xml` | [LBK nr. 395 af 13/04/2023](https://www.retsinformation.dk/eli/lta/2023/395) | Current SU Act entry used for section 7(3). |
| `raw/LOV_761_2026_SU_loven_aendring.xml` | [LOV nr. 761 af 08/09/2026](https://www.retsinformation.dk/eli/lta/2026/761) | Latest enacted amendment recorded at the status-check date. |

The received XHAILe source file is the 2025 guidance snapshot in
`../../../XHAILE_determinations_SUlov-main/su-handicap[38645].txt`. It remains
the provenance source for the determination mapping but is not the active
current-law answer key.

## Refresh Rule

Before final empirical runs, verify each official page's status and later
amendments. If a source has changed, preserve these files, add the successor as
a new version, remap the 14 passages, regenerate the benchmark and rerun the
full validator and regression suite. Do not silently overwrite a source used by
an already reported run.
