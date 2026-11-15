# V5 Ten-Criterion Answer Rubric

> **C04-aligned variant (15 November 2026).** This file is a copy of `TEN_CRITERIA_JUDGE_RUBRIC_V5.md` (left unchanged) in which only the C04 `met` column is replaced by the legal reviewer's exact wording from the review tool (`scripts/simple_review.py`). It is used only for the sensitivity rerun in `outputs/v5_judge_c04_aligned/`, together with `prompts/llm_judge_prompt_v3_c04_reviewer_wording.txt`. The original run and its records are untouched.

> **Agent Metadata**
> - **Document type:** Manual and LLM-judge coding rubric.
> - **Thesis role:** Defines the same ten answer-level decisions for the human reference review and the blind LLM judge in the V5 pilot.
> - **Use when:** Coding the selected ten SU-guidance answers, preparing the LLM-judge prompt or comparing human and automated decisions.
> - **Do not use for:** Individual entitlement decisions, a general model ranking, replacing qualified legal review or claiming that XHAILe/DCR was tested as an integrated system.
> - **Key concepts:** legal correctness, completeness, source traceability, source validity, claim support, unsupported additions, qualifications, reasoning, legal modality, LLM-as-judge.
> - **Source basis:** Based on the legal input of Patrick Michel and formulated by the researcher and Patrick Michel together after the review meeting, informed by the earlier specialist interviews, the approved V4 rubrics and the supervisor feedback.
> - **Evidence status:** V5 coding protocol; no human--LLM agreement result exists until both sheets are completed and compared.
> - **Read depth:** Read fully before any V5 coding.
> - **Related files:** `../docs/EVALUATION_PROTOCOL_V5.md`, `../benchmark/judge_subset_su_guidance_v5.csv`, `../prompts/llm_judge_prompt_v1.txt`, `SCORING_RUBRIC.md`.
> - **Last updated:** 2026-11-06

## Status 2026-11-06 (gælder frem for ældre afsnit i denne fil)

- **Evaluering gennemført:** GPT-6-luna (`gpt-6-luna`) og Llama 3.3 70B Instruct (Q8_0, UCloud) har svaret på alle 14 spørgsmål i question-only og correct-source = 56 svar.
- **Menneskelig reference:** Den juridiske reviewer (Patrick Michel) vurderede alle 56 svar selv i fire runder (Llama uden kilde, GPT uden kilde, Llama med kilde, GPT med kilde) = 560 beslutninger. Alle endelige labels er reviewerens egne vurderinger. Tre labels blev rettet efter kildereglen (`Evaluation/outputs/v5_review/human_label_corrections.csv`).
- **LLM-judge:** Claude Sonnet 5.5 (`claude-sonnet-5-5`), tre kørsler, blind for menneskelige labels.
- **Resultater (rapport kap. 6):** juridisk dækkende (C01+C02) 1/28 uden kilde → 18/28 med kilde; C04 1/56; enighed på 7 bedømmelseskriterier 79,3 % (κ 0,60), C04-C06 separat 97,6 %, alle ti 84,8 % (κ 0,77); 83/85 uenigheder har judge som den strengeste.
- **Self-retrieval:** Forskerens eget RAG-system er tredje svarbetingelse (self-retrieval), ikke "bounded contrast". Kørslen er endnu ikke udført; rapporten har markører `% INSERT AFTER SELF-RETRIEVAL RUN`. Patrick Michel vurderer også self-retrieval-svarene, og LLM-judge kører tre gange som for de øvrige. Hvis kørslen ikke gennemføres før aflevering, skal metodeteksten rettes tilbage.
- **Rammeværk:** "layered assurance model" med syv lag (kap. 2, `tab:layered-model-map`).
- **SQ4:** Forfatteren besluttede 2026-11-06, at SQ4 bliver som den står. Forskellen uden/med kilde dækkes af SQ1 og SQ3 (tabel 3.1).
- **Kontrol:** `Status/FULL_THESIS_REVIEW_2026-11-06.md` (trin 1-8 udført).


## Purpose

V5 changes the evaluation question. The pilot no longer tries to create a broad
ranking from a small dataset. It asks whether an LLM judge can reproduce a
careful human assessment of legal AI answers, and where the two forms of review
disagree.

The human reviewer and the LLM judge receive the same review material:

- the Danish question;
- the model answer;
- the frozen current source passages;
- the approved question-specific expert rubric; and
- these ten shared criteria.

The LLM judge never receives the human decisions. The human reviewer never
changes a decision after seeing the LLM labels unless the change is recorded as
a separate adjudication.

## Criterion Groups

| Group | Criteria |
|---|---|
| Source | C04, C05, C06, C07 |
| Legal | C01, C02, C08, C10 |
| Support | C03, C09 |

## Decision Labels

Use one label for every criterion.

| Label | Meaning |
|---|---|
| `met` | The answer satisfies the criterion within the frozen task and review material. |
| `not_met` | The answer fails the criterion, including through a material omission or contradiction. |
| `not_assessable` | The available answer or review material does not permit a defensible decision. This is not a neutral or passing label. |

Every label requires a short reason tied to the answer, source passage or
expert rubric. Do not use outside legal knowledge to repair the answer.

## The Ten Criteria

| ID | Criterion | Operational question | `met` requires |
|---|---|---|---|
| C01 | Overall legal correctness | Is the answer legally correct within the frozen task? | The conclusion and material legal statements agree with the approved expert rubric and current sources, with no material legal error. |
| C02 | Required elements complete | Does the answer contain everything the expert rubric marks as critical? | Every critical element is communicated. Equivalent wording is accepted. |
| C03 | Direct relevance | Does the answer respond to the question asked? | The answer addresses every material part of the question without relying on irrelevant text in place of an answer. |
| C04 | Source traceability | Can the material legal statements be connected to identifiable sources? | Met: material statements are attributed to an identifiable source (statute, provision or guidance). Not met: no identifiable source is cited. |
| C05 | Source validity | Are the stated sources suitable for this task? | The cited sources exist and are current, authoritative and applicable within the frozen source boundary. |
| C06 | Claim--source support | Do the stated sources support what the answer says? | The cited passages support the full material meaning of every legal claim. A merely related passage is insufficient. |
| C07 | No unsupported legal additions | Does the answer avoid invented or unsubstantiated legal content? | No material rule, condition, exception, threshold, authority or legal effect lacks support in the review material. |
| C08 | Qualifications and exceptions preserved | Does the answer retain the limits that change the legal meaning? | Required qualifications, exceptions, temporal limits and non-absolute wording in the expert rubric are preserved. |
| C09 | Reasoning coherence | Does the explanation support its own conclusion? | The legal steps are mutually consistent and the conclusion follows from the rules or distinctions stated in the answer. A correct conclusion reached through contradictory reasoning fails. |
| C10 | Legal modality precision | Does the answer distinguish what is required, allowed, excluded or discretionary? | Words such as *must*, *may*, *normally* and *as a starting point* reflect the source and do not turn guidance, discretion or exceptions into absolute rules. |

## Coding Rules

1. Code the answer that was produced. Do not silently rewrite it.
2. Assess all ten criteria independently. A failure on C04 does not
   automatically decide C01, and a correct conclusion does not automatically
   pass C06 or C09.
3. C01 is deliberately retained as an overall correctness decision. The other
   nine criteria explain why an answer passes or fails rather than replacing
   correctness with a proxy such as hallucination detection.
4. C02, C08 and C10 use the question-specific expert rubric. C04--C07 use the
   source locators and frozen passages. C09 concerns the reasoning visible in
   the answer, not hidden model reasoning.
5. If one material claim fails an all-claims criterion such as C06 or C07, the
   answer receives `not_met` for that criterion. Record the failed claim in the
   reason.
6. Do not add the ten labels into a total score. Report criterion profiles,
   agreement and disagreements separately.
7. Source dependency between C04, C05 and C06: if the answer cites no
   identifiable source, C04 is `not_met` and C05 and C06 are `not_assessable`,
   because the validity of a source and its support for a claim cannot be
   judged when no source is given. If the answer cites a source, all three
   criteria are coded as `met` or `not_met`. The rule has been part of the
   LLM-judge prompt (`../prompts/llm_judge_prompt_v2.txt`) since 4 November
   2026 and of the review tool's decision rules before the human assessment;
   it was added to this rubric on 5 November 2026. It applies equally to the
   human reference and the LLM judge.

## Human Reference And LLM Judge

The initial human sheet is completed by the researcher. A qualified legal
reviewer must then check and approve or correct the final human labels before
they are treated as the comparison reference. The existing approval of the
question-specific V4 rubrics does not by itself validate the later coding of
model answers.

The LLM judge uses a frozen model, prompt and input package. It must return one
decision and one short reason for every criterion. Its labels are compared with
the legally checked human sheet using counts, raw agreement and Cohen's kappa
where estimable. No agreement threshold is defined in advance, and high
agreement is not treated as proof that automated legal evaluation can replace
human review.
