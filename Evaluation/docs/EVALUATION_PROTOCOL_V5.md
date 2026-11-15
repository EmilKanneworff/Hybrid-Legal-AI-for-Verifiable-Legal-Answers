# Evaluation Protocol V5: Ten Questions, Ten Criteria and an LLM Judge

> **Agent Metadata**
> - **Document type:** Versioned evaluation protocol.
> - **Thesis role:** Defines the new bounded pilot in which human and LLM-judge coding are compared on ten selected SU-guidance questions.
> - **Use when:** Writing Chapters 3, 6 or 8; preparing human coding; preparing the LLM judge; or interpreting agreement and disagreement.
> - **Do not use for:** A model leaderboard, population-level performance estimates, a claim that automated judging is validated before comparison, or a claim that XHAILe/DCR was tested as a complete system.
> - **Key concepts:** ten-question subset, ten criteria, manual coding, legal review, LLM-as-judge, agreement, bounded scalability.
> - **Source basis:** Frozen V4 cases and outputs, Patrick Michel's approved question rubrics, Daniel Hardt supervision feedback supplied on 4 November 2026, Raina et al. (2026), and the active thesis evaluation framework.
> - **Evidence status:** Final. The evaluation is complete; see the final status note below.
> - **Read depth:** Read fully before changing or running the V5 evaluation.
> - **Related files:** `../benchmark/judge_subset_su_guidance_v5.csv`, `../scoring/TEN_CRITERIA_JUDGE_RUBRIC_V5.md`, `../prompts/llm_judge_prompt_v1.txt`, `V4_FINAL_RUN_STATUS_2026-11-04.md`, `EVALUATION_PROTOCOL_V4.md`.
> - **Last updated:** 2026-11-10

> **Final status (10 November 2026).** The evaluation is complete. The final design has 14 questions, three answer conditions and five runs with 70 answers. The legal reviewer, Patrick Michel, assessed all 70 answers himself in five rounds, and the LLM judge assessed them in three runs without seeing his labels. Where the sections below describe a ten-question subset or a first coding by the researcher, they record the earlier plan, which this procedure replaced. The section "Human Reference And LLM Judge" in `../scoring/TEN_CRITERIA_JUDGE_RUBRIC_V5.md` also describes that earlier plan. It is kept unchanged because the rubric was sent to the LLM judge exactly as it stands, and its text is part of the recorded prompt hashes. The results are summarised in `../outputs/v5_review/results/README.md`.

## Why V5 Exists

The small SU dataset cannot support a general claim that one model or input
condition is better than another. Its stronger contribution is methodological:
the answers can be examined in depth against explicit legal and source-based
criteria.

V5 therefore changes the main evaluation question to:

> To what extent does a frozen LLM judge reproduce a legally checked human
> assessment of the same legal AI answers across ten explicit criteria, and
> where do the two forms of assessment disagree?

## Status 2026-11-06 (gælder frem for ældre afsnit i denne fil)

- **Evaluering gennemført:** GPT-6-luna (`gpt-6-luna`) og Llama 3.3 70B Instruct (Q8_0, UCloud) har svaret på alle 14 spørgsmål i question-only og correct-source = 56 svar.
- **Menneskelig reference:** Den juridiske reviewer (Patrick Michel) vurderede alle 56 svar selv i fire runder (Llama uden kilde, GPT uden kilde, Llama med kilde, GPT med kilde) = 560 beslutninger. Alle endelige labels er reviewerens egne vurderinger. Tre kildelabels blev ændret, da kildereglen var klar for revieweren (de første labels: `Evaluation/outputs/v5_review/simple_reviews_before_source_rule_2026-11-05.csv`).
- **LLM-judge:** Claude Sonnet 5.5 (`claude-sonnet-5-5`), tre kørsler, blind for menneskelige labels. C04 er formuleret præcis som i juristens værktøj (`prompts/llm_judge_prompt_v3_c04_reviewer_wording.txt`).
- **Resultater (rapport kap. 6):** juridisk dækkende (C01+C02) 1/28 uden kilde → 18/28 med kilde; C04 1/56; enighed på 7 bedømmelseskriterier 79,1 % (κ 0,59), C04-C06 separat 97,6 %, alle ti 84,6 % (κ 0,76); 83/86 uenigheder har judge som den strengeste.
- **Self-retrieval (gennemført 2026-11-08):** Forskerens eget RAG-system (svarmodel GPT-6-luna) er tredje svarbetingelse. Svarene er kopieret manuelt fra systemets brugerflade, run `20261108T182544618580Z`. Patrick Michel bedømte de 14 svar i runde 5, så det samlede datasæt er 70 svar og 700 menneskelige beslutninger. LLM-dommeren kørte tre gange, i alt 2.100 beslutninger. Resultater for GPT-6-luna uden kilde / med korrekt kilde / med hentet kilde: juridisk tilstrækkelig 1/12/4 af 14, C04 0/1/14, C06 0/1/6, C07 4/14/8. Dommer mod jurist på de 14: 7 bedømmelseskriterier 69,4 % (κ 0,43), C04-C06 73,8 % (κ 0,46), dommeren strengest i 39 af 41 uenigheder. Kernefundet er, at sporbarhed og korrekthed skilles ad: alle svar viste kilder, men kun 4 var tilstrækkelige. Rapporten er opdateret i kap. 1, 3, 5, 6 (ny tabel 6.6), 7, 8, 9 og abstract. Alle CHECK- og INSERT-markører er fjernet. Data ligger i `Evaluation/outputs/v5_judge_c04_aligned/results/judge_agreement_subsets.csv`.
- **Self-retrieval-kørsel (2026-11-08):** Emils RAG-system (svarmodel GPT-6-luna) svarede på de 14 spørgsmål. Svarene blev kopieret manuelt ind (run `20261108T182544618580Z`), og en dobbelt gemning er arkiveret i `outputs/v5_cleared/`. Patrick Michel bedømte alle 14 i runde 5, før dommeren så dem. LLM-dommerens `max_tokens` er hævet fra 4096 til 16000 og timeout fra 180 til 300 sek., fordi Claude Sonnet 5.5's adaptive tænkning tæller med i loftet, og det længste self-retrieval-svar (spm. 1) ramte loftet tre gange (`stop_reason: max_tokens`). Loftet ses ikke af modellen og ændrer ikke bedømmelsesproceduren. Alle 168 tidligere dommerbedømmelser sluttede med `end_turn` under 4096 tokens (maks. 4078).
- **Rammeværk:** "layered assurance model" med syv lag (kap. 2, `tab:layered-model-map`).
- **SQ4:** Forfatteren besluttede 2026-11-06, at SQ4 bliver som den står. Forskellen uden/med kilde dækkes af SQ1 og SQ3 (tabel 3.1).
- **Kontrol:** `Status/FULL_THESIS_REVIEW_2026-11-06.md` (trin 1-8 udført).


The design follows Daniel Hardt's supervision feedback that correctness must be
assessed directly, that absence of hallucination is not sufficient, and that a
small in-depth coding exercise can be used to explore whether later evaluation
could be scaled with an LLM judge. The design also follows the caution in Raina
et al. (2026): consistency within an LLM judge is not the same as agreement with
trained human legal assessment.

## Version Boundary

V4 remains frozen and preserved. It contains 14 questions, approved expert
rubrics and two complete answer-generation runs. V5 does not overwrite those
records or relabel them as new model runs.

V5 is a secondary evaluation of a pre-declared subset of the V4 outputs:

| Element | V5 scope |
|---|---|
| Questions | 10 selected V4 questions |
| Conditions | `closed_book` and `gold_context`, kept separate |
| Answers | 20 existing answers: 10 per condition |
| Generated legal claims | 45 closed-book and 66 correct-source claims in the selected answers |
| Shared criteria | 10 answer-level criteria |
| Human decisions | 200 labels before reasons: 20 answers x 10 criteria |
| LLM-judge decisions | 200 labels before reasons: the same 20 answers x 10 criteria |

The original V4 run IDs, prompts, model identifiers, hashes and raw outputs
remain the generation provenance.

## Selection Of Ten Questions

The selection is fixed in
`benchmark/judge_subset_su_guidance_v5.csv`. Questions were selected for topic
coverage before answer-quality coding. The retained set covers general
eligibility, permanence, severity, multiple impairments, work-capacity scope,
application documentation, medical documentation, a medical certificate, a
specialist declaration and an advisory opinion from Arbejdsmarkedets
Erhvervssikring.

Four questions are excluded to reduce repeated subtopics rather than because of
their model answers:

- Questions 6 and 7 overlap with the broader work-capacity scope in Question 5;
- Question 10 is a narrower documentation variant alongside Questions 8 and 9;
- Question 12 overlaps with the retained supplementary-evidence questions.

All ten retained questions already have an approved V4 expert rubric. This
preserves the legal reference work without claiming that Patrick Michel has
reviewed later human or LLM-judge labels.

## Review Material

Both judges receive the same material for each answer:

1. the question;
2. the raw answer;
3. the current frozen source passages;
4. the approved question-specific expert rubric, including critical elements,
   material errors, acceptable variants and required qualifications; and
5. the shared ten-criterion V5 rubric.

The human and LLM judges do not receive each other's labels. No web search or
outside legal source may be used during coding. A source gap is recorded rather
than repaired from memory.

## Ten Shared Criteria

The operational rules are canonical in
`scoring/TEN_CRITERIA_JUDGE_RUBRIC_V5.md`:

1. overall legal correctness;
2. required elements complete;
3. direct relevance;
4. source traceability;
5. source validity;
6. claim--source support;
7. no unsupported legal additions;
8. qualifications and exceptions preserved;
9. reasoning coherence; and
10. legal modality precision.

Each criterion receives `met`, `not_met` or `not_assessable` and a short reason.
If an answer cites no identifiable source, C04 is `not_met` and C05 and C06
are `not_assessable`; if it cites a source, all three are coded `met` or
`not_met` (rule 7 in `scoring/TEN_CRITERIA_JUDGE_RUBRIC_V5.md`).
No composite score is calculated.

## Human Reference Procedure

1. Generate one V5 sheet for each retained run.
2. The researcher codes all ten criteria independently for every answer.
3. A qualified legal reviewer checks the completed human sheet against the
   frozen passages and expert rubrics.
4. Corrections are recorded in a separate checked sheet; the original
   researcher sheet is retained.
5. Only the legally checked sheet is used as the human comparison reference.

The expert's earlier approval of the answer rubrics and the later check of model
answer coding are different controls. V5 results remain provisional until the
second control is complete.

## LLM-Judge Procedure

1. Freeze the judge provider, exact model ID, date, prompt, decoding settings
   and input hashes.
2. Give the judge the same review material but no human labels.
3. Require the JSON structure in `prompts/llm_judge_prompt_v1.txt`.
4. Retain raw judge output and parsing status.
5. Do not retry a substantive disagreement. Retry only a provider or schema
   failure under the same frozen configuration.

The judge model and the answer-generating model must both be disclosed. If they
are the same model or model family, this is reported as a possible same-model
bias rather than hidden.

## Comparison

Compare the legally checked human labels and the LLM labels by criterion and
across all criteria. Report:

- paired decisions and missing decisions;
- agreement and disagreement counts;
- raw agreement;
- Cohen's kappa where category variation makes it estimable; and
- a qualitative account of the disagreements.

The analysis should ask which distinctions are difficult for the LLM judge.
For example, it may agree on missing citations but disagree on whether a source
supports the full legal meaning or whether a qualification changes the answer.
Those disagreement patterns are more informative than one overall percentage.

## What V5 Can And Cannot Show

V5 can show whether one frozen LLM judge agrees with one legally checked human
reference on this small set of SU-guidance answers. It can also identify which
criteria create disagreements and whether automated coding appears useful for
screening or first-pass review.

V5 cannot establish that:

- the judge is generally valid across legal domains;
- an LLM can replace a lawyer or legal reviewer;
- one answer-generating condition or provider is generally superior;
- a high agreement percentage proves legal correctness;
- the evaluation scales without further validation; or
- XHAILe or DCR was tested as an integrated system.

Any claim about scalability is therefore conditional: the pilot can indicate
whether LLM-assisted coding is worth testing at a larger scale, while the
human/legal reference remains necessary.

## Current Status And Release Gates

The ten-question selection, source material, expert rubrics and two parent V4
runs exist. The selected subset contains 20 answers and 111 generated claims.
The following work remains:

- generate and complete the researcher coding sheets;
- obtain legal checking of the final human labels;
- run one frozen LLM judge on the same 20 answers;
- compare the two label sets; and
- inspect and explain all disagreements.

Until those steps are complete, the thesis may describe the V5 design and the
existing answer-generation records, but it may not report human--LLM agreement
or claim that the judge can scale the evaluation.
