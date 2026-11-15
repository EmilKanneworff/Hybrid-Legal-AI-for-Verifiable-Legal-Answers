# Forslag: skarpere formulering af de 14 testspørgsmål

> **Agent Metadata**
> - **Document type:** Revisionsforslag til juridisk reviewer (dansk).
> - **Thesis role:** Grundlag for Patrick Michels godkendelse af nye spørgsmålsformuleringer før de endelige svarkørsler.
> - **Use when:** Spørgsmålssættet revideres efter reviewerens feedback (optagelse "Viborggade 26 5.m4a", 00:09:00–00:09:48).
> - **Do not use for:** Evidens for modelsvarenes kvalitet. Status: godkendt af Patrick Michel 2026-11-05.
> - **Key concepts:** V4 testspørgsmål, forventet svar, XHAILe-punkter, spørgsmålsrevision.
> - **Source basis:** `benchmark/testcases_su_guidance_qa_v4.jsonl`, `benchmark/expert_answer_criteria_su_guidance_qa_v4.csv`, reviewerens mundtlige feedback.
> - **Evidence status:** Godkendt. Patrick Michel sagde OK til alle 14 forslag og til at fjerne "vejledningen" fra spørgsmålene (bekræftet af forfatteren 2026-11-05). Gemt som `benchmark/testcases_su_guidance_qa_v5.jsonl` og `benchmark/expert_answer_criteria_su_guidance_qa_v5.csv`.
> - **Read depth:** Fuld læsning før godkendelse.
> - **Related files:** `PATRICK_MICHEL_EXPERT_RUBRIC_APPROVAL_2026-11-01.md`, `../benchmark/testcases_su_guidance_qa_v4.jsonl`.
> - **Last updated:** 2026-11-05

## Formål

Patrick påpegede, at spørgsmålene skal være skarpe, så svaret er nemt at
vurdere. Eksempel: "Hvilke overordnede betingelser …" er en
fortolkningssag. Det skarpe spørgsmål er "Hvad er betingelserne?".

Principper for forslaget:

1. Ét klart spørgsmål. Højst to dele, og kun når det forventede svar kræver det.
2. Ingen "angiver vejledningen om …". Spørgsmålet stilles som en borger eller
   sagsbehandler ville stille det.
3. Spørgsmålet beder om netop det, som det forventede svar indeholder. En model
   skal ikke kunne tabe point for noget, spørgsmålet ikke bad om.
4. De XHAILe-punkter, spørgsmålet bygger på, og den korrekte kilde ændres ikke.

## Til Patrick: tre ting at tage stilling til

- **A.** Er hvert nyt spørgsmål skarpt nok?
- **B.** Passer det forventede svar stadig til det nye spørgsmål? (Det
  forventede svar står i review-siden under "Questions and data".)
- **C.** Skal spørgsmålet nævne vejledningen? Forslaget fjerner det. Fordel:
  mere naturligt spørgsmål. Ulempe: en model uden kilde kan svare ud fra loven,
  forarbejder eller praksis i stedet for vejledningen.

## De 14 spørgsmål

| Nr. | Nu | Forslag | Patrick: OK / ret til |
|---|---|---|---|
| 01 | Hvilke overordnede betingelser og uddannelseskrav angiver vejledningen om SU-handicaptillæg for, at en uddannelsessøgende kan få handicaptillæg? | Hvad er betingelserne for at få SU-handicaptillæg? | |
| 02 | Hvad angiver vejledningen om SU-handicaptillæg om kravet om, at den uddannelsessøgendes funktionsnedsættelse skal være varig, herunder når den ikke fra begyndelsen kan betragtes som varig eller kronisk? | Hvornår er en funktionsnedsættelse varig i forhold til SU-handicaptillæg, og hvad gælder, hvis den ikke er varig eller kronisk fra begyndelsen? | |
| 03 | Hvilke forhold indgår efter vejledningen om SU-handicaptillæg i vurderingen af den uddannelsessøgendes funktionsnedsættelses sværhedsgrad? | Hvad lægger Udbetaling Danmark vægt på, når sværhedsgraden af en funktionsnedsættelse vurderes i en sag om SU-handicaptillæg? | |
| 04 | Hvordan håndterer Udbetaling Danmark efter vejledningen om SU-handicaptillæg flere funktionsnedsættelser hos samme uddannelsessøgende, og hvilke af dem indgår som udgangspunkt i vurderingen? | En ansøger om SU-handicaptillæg har flere funktionsnedsættelser. Hvilke af dem vurderer Udbetaling Danmark? | |
| 05 | Hvordan vurderes erhvervsevne ved SU-handicaptillæg, og hvilken betydning har kommunal arbejdsevnevurdering, arbejdsprøvning, særlig arbejdspladsindretning, arbejdsgiverkontakt, arbejdets studierelevans, lokale jobmuligheder og erhvervsevnen efter uddannelsen? | Indgår følgende i vurderingen af erhvervsevnen ved SU-handicaptillæg: kommunal arbejdsevnevurdering, arbejdsprøvning, særlig arbejdspladsindretning, kontakt til arbejdsgiver, om arbejdet er studierelevant, lokale jobmuligheder og erhvervsevnen efter uddannelsen? | |
| 06 | Hvilke oplysninger om arbejdstimer, indkomst og tidligere eller aktuelt erhvervsarbejde kan efter vejledningen om SU-handicaptillæg indgå i vurderingen af den uddannelsessøgendes erhvervsevne? | Hvilke oplysninger om arbejde og indkomst bruger Udbetaling Danmark, når erhvervsevnen vurderes i en sag om SU-handicaptillæg? | |
| 07 | Hvad vurderer Udbetaling Danmark efter vejledningen om SU-handicaptillæg, hvis den uddannelsessøgende oplyser, at et arbejde er ophørt på grund af funktionsnedsættelsen? | En ansøger om SU-handicaptillæg har måttet stoppe et arbejde på grund af sin funktionsnedsættelse. Giver det i sig selv ret til tillægget, og hvad vurderer Udbetaling Danmark? | |
| 08 | Hvad bør dokumentationen til en ansøgning om SU-handicaptillæg som udgangspunkt indeholde, hvis den uddannelsessøgendes behandlingsforløb er afsluttet? | Hvilken lægelig dokumentation skal en ansøgning om SU-handicaptillæg indeholde, når behandlingen er afsluttet? | |
| 09 | Hvilke oplysninger fremhæver vejledningen om SU-handicaptillæg, at den lægefaglige dokumentation skal beskrive? | Hvad skal den lægelige dokumentation beskrive i en ansøgning om SU-handicaptillæg? | |
| 10 | Hvilke oplysninger og former for dokumentation fremhæver vejledningen om SU-handicaptillæg ved en medfødt funktionsnedsættelse? | Hvilken dokumentation kan en ansøger med en medfødt funktionsnedsættelse sende med en ansøgning om SU-handicaptillæg? | |
| 11 | Hvad kan Udbetaling Danmark efter vejledningen om SU-handicaptillæg gøre, hvis den uddannelsessøgendes funktionsniveau ikke kan vurderes ud fra den indsendte dokumentation, og hvad skal en eventuel lægeattest belyse? | Hvad kan Udbetaling Danmark gøre, hvis dokumentationen ikke er nok til at vurdere ansøgerens funktionsniveau i en sag om SU-handicaptillæg, og hvad skal en lægeattest så beskrive? | |
| 12 | I hvilke situationer kan Udbetaling Danmark efter vejledningen om SU-handicaptillæg indhente en aktuel redegørelse fra en speciallæge eller et hospital? | Hvornår kan Udbetaling Danmark indhente en aktuel redegørelse fra en speciallæge eller et hospital i en sag om SU-handicaptillæg? | |
| 13 | Hvornår kan Udbetaling Danmark efter vejledningen om SU-handicaptillæg anmode om en speciallægeerklæring, og hvilke eksempler på begrundelser nævnes? | Hvornår kan Udbetaling Danmark bede om en speciallægeerklæring i en sag om SU-handicaptillæg? | |
| 14 | Hvilke forhold angiver vejledningen om SU-handicaptillæg, at en vejledende udtalelse fra Arbejdsmarkedets Erhvervssikring skal belyse? | Hvad skal en udtalelse fra Arbejdsmarkedets Erhvervssikring belyse i en sag om SU-handicaptillæg, og er Udbetaling Danmark bundet af den? | |

## Noter til enkelte spørgsmål

- **05:** Listen står stadig i spørgsmålet, men nu som et ja/nej-spørgsmål pr.
  punkt. Det forventede svar er "nej" til alle syv, og det gør svaret nemt at
  vurdere punkt for punkt.
- **07:** "Giver det i sig selv ret til tillægget?" er tilføjet, fordi det
  forventede svar siger, at arbejdsophøret ikke i sig selv giver ret.
- **14:** "Er Udbetaling Danmark bundet af den?" er tilføjet, fordi det
  forventede svar siger, at udtalelsen er vejledende.

## Når spørgsmålene er godkendt

1. Spørgsmålene gemmes som en ny version. V4-filen ændres ikke.
2. Forventede svar, der skal rettes, rettes og godkendes med dato.
3. De to prøvekørsler fra 4. november ryddes ("Clear answers"), fordi de
   brugte de gamle spørgsmål.
4. Svarkørslerne køres med de nye spørgsmål.
5. Patrick og Emil gennemgår alle svar sammen og udfylder alle ti kriterier.
6. Rapporten og bilaget opdateres med den nye version og datoen.
