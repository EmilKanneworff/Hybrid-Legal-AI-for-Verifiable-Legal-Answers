# Guidance version check, VEJ nr. 10157 against VEJ nr. 10278

> **Agent Metadata**
> - **Document type:** Check record for the evaluation sources.
> - **Thesis role:** Documents the sentence in Section 6.2 that the guidance used in the evaluation was later replaced with editorial changes only.
> - **Use when:** Checking which version of the guidance the evaluation used and what changed afterwards.
> - **Do not use for:** Legal interpretation of the guidance.
> - **Source basis:** The two texts as shown on retsinformation.dk on 16 November 2026.
> - **Evidence status:** Workspace command output (word comparison), saved with the two texts.
> - **Last updated:** 2026-11-16

## What was checked

The evaluation of 5 November 2026 used *VEJ nr. 10157 af 05/10/2026*. On 16 November 2026, retsinformation.dk shows that document as "Historisk" and *VEJ nr. 10278 af 05/10/2026* as "Gældende", and the new document lists VEJ nr. 10157 under "Ændrer i/ophæver".

- https://www.retsinformation.dk/eli/retsinfo/2026/10157
- https://www.retsinformation.dk/eli/retsinfo/2026/10278

I saved the text of both documents as shown on those pages (from "Yderligere oplysninger" to the end) and compared them word by word.

| File | SHA-256 |
|---|---|
| `VEJ_10157_retsinformation_text_2026-11-16.txt` | `976a0e4490f26b2132c3226f5775f6ebe6964137b58b3e09c626f36582a2ae38` |
| `VEJ_10278_retsinformation_text_2026-11-16.txt` | `fc625c56e9e60ab2d683001b8ce1b79c81cca1564fba14f266d2b8d9f4bf9883` |

## Result for the whole text

The texts have 7,212 and 7,220 words and differ in 12 places. In eight places the word "styrelsen" (or "styrelse") became "Udbetaling Danmark". The other four differences are one heading, "Forhold, der indgår ikke …", which became "Forhold, der ikke indgår …" in the table of contents and in the text.

| # | Words before | VEJ nr. 10157 | VEJ nr. 10278 | Words after |
|---|---|---|---|---|
| 1 | … i vurderingen? 3. 6 Forhold, der | (nothing) | ikke | indgår ikke i Udbetaling … |
| 2 | … vurderingen? 3. 6 Forhold, der indgår | ikke | (nothing) | i Udbetaling Danmarks vurdering … |
| 3 | … sig erhvervsarbejde. Konkret betyder det, at | styrelsen, | Udbetaling Danmark, | med udgangspunkt i de … |
| 4 | … skal vedlægges på ansøgningstidspunktet. Det er | styrelsen, | Udbetaling Danmark, | som vurderer, om der … |
| 5 | … for denne funktionsnedsættelse. 3.6 Forhold, der | (nothing) | ikke | indgår ikke i Udbetaling … |
| 6 | … denne funktionsnedsættelse. 3.6 Forhold, der indgår | ikke | (nothing) | i Udbetaling Danmarks vurdering … |
| 7 | … sig gældende, vil blive afvist af | styrelse | Udbetaling Danmark | uden realitetsbehandling, da minimumskravet … |
| 8 | … hvornår oplysningerne skal være sendt til | styrelsen. | Udbetaling Danmark. | Er det ikke muligt … |
| 9 | … forbindelse med ovenstående indhentning afholdes af | styrelsen. | Udbetaling Danmark. | 5.1.3 Anmoder om yderligere … |
| 10 | … handicaptillæg, men er ikke bindende for | styrelsen. | Udbetaling Danmark. | Udbetaling Danmark betaler eventuelle … |
| 11 | … Statens Uddannelsesstøtteordninger. Klagen skal sendes til | styrelsen. | Udbetaling Danmark. | Det er vigtigt at … |
| 12 | … Statens Uddannelsesstøtteordningers afgørelser er bindende for | styrelsen, | Udbetaling Danmark, | og at den uddannelsessøgende … |

## Result for the passages used in the test

The 14 questions use 123 sentences from the guidance as source passages (`testcases_su_guidance_qa_v5.jsonl`, sentences over 40 characters). All 123 are found word for word in VEJ nr. 10157, and 121 are found word for word in VEJ nr. 10278. The other 2 differ only in the name of the authority.

| Question | Sentence in the test (VEJ nr. 10157) |
|---|---|
| 11 | Eventuelle udgifter i forbindelse med ovenstående indhentning afholdes af styrelsen. |
| 14 | Udtalelsen indgår i Udbetaling Danmarks vurdering af, om den uddannelsessøgende er berettiget til handicaptillæg, men er ikke bindende for styrelsen. |

In both sentences, "styrelsen" became "Udbetaling Danmark" in VEJ nr. 10278. The cited sections of the thesis (3.1, 4.1, 5.1.3.1, 5.1.3.2, 6.1.1 and 7) are otherwise unchanged.

## Limits

The comparison covers the text as shown on retsinformation.dk on the day of the check. It does not assess whether the change of the authority's name has any legal effect.
