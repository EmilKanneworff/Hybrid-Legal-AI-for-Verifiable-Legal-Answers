"""Agreement statistics (Chapter 6 and Appendix E) for a judge CSV with repeats 1-3.
Usage: python3 Evaluation/scripts/agreement_report_v5.py Evaluation/outputs/v5_judge_c04_aligned/ai_review_c04_aligned.csv [--csv OUT.csv]
Added 15 November 2026."""
import csv, sys, collections
from pathlib import Path
E=str(Path(__file__).resolve().parents[1]/'outputs')+'/'
CR=['c01_overall_legal_correctness','c02_required_elements_complete','c03_direct_relevance','c07_no_unsupported_legal_additions','c08_qualifications_and_exceptions','c09_reasoning_coherence','c10_legal_modality_precision','c04_source_traceability','c05_source_validity','c06_claim_source_support']
JUDG=CR[:7]; SRC=CR[7:]
key=lambda r:(r['run_id'],r['case_id'],r['input_mode'])
H={key(r):r for r in csv.DictReader(open(E+'v5_review/simple_reviews.csv',encoding='utf-8'))}
R={1:{},2:{},3:{}}
for r in csv.DictReader(open(sys.argv[1],encoding='utf-8')):
    R[int(r['repeat'])][key(r)]=r
J=R[1]
first=[k for k in H if k[2]!='self_retrieval']; own=[k for k in H if k[2]=='self_retrieval']
cb=[k for k in H if k[2]=='closed_book']; gc=[k for k in H if k[2]=='gold_context']
def kappa(pairs):
    n=len(pairs); po=sum(a==b for a,b in pairs)/n
    ca=collections.Counter(a for a,_ in pairs); cb_=collections.Counter(b for _,b in pairs)
    pe=sum(ca[k]*cb_[k] for k in set(ca)|set(cb_))/n/n
    return (po-pe)/(1-pe) if pe<1 else 1.0
def pairs(keys,crit): return [(H[k][c+'_label'],J[k][c+'_label']) for k in keys for c in crit]
def line(name,keys,crit,stable=True):
    p=pairs(keys,crit); a=sum(x==y for x,y in p)
    st=''
    if stable and len(crit)==1 and all(keys[0] in R[i] for i in (1,2,3)):
        c=crit[0]; s=sum(1 for k in keys if len({R[i][k][c+'_label'] for i in (1,2,3)})==1); st=f'{s}/{len(keys)}'
    print(f'{name:38s} {a}/{len(p)}  {100*a/len(p):5.1f}  k={kappa(p):.2f}  stable={st}')
print('== FIRST 56, per criterion (Appendix E)')
for c in CR: line(c,first,[c])
line('SEVEN JUDGEMENT',first,JUDG,False); line('THREE SOURCE',first,SRC,False); line('ALL TEN',first,CR,False)
def dis(keys,crit):
    d=[(x,y) for x,y in pairs(keys,crit) if x!=y]
    st=[(x,y) for x,y in d if y=='not_met']
    return len(d),len(st),collections.Counter(x for x,y in st)
print('first 56 all ten disagreements (n, judge Not met, reviewer label when judge Not met):',dis(first,CR))
print('first 56 judgement: correct source',end=' '); p=pairs(gc,JUDG); print(f'{100*sum(x==y for x,y in p)/len(p):.1f}%', end='  without source '); p=pairs(cb,JUDG); print(f'{100*sum(x==y for x,y in p)/len(p):.1f}%')
print('== OWN RAG 14')
line('SEVEN JUDGEMENT',own,JUDG,False); line('THREE SOURCE',own,SRC,False); line('ALL TEN',own,CR,False)
print('own RAG all ten disagreements:',dis(own,CR)[:2])
print('== FIGURE values (rounded %): own RAG | first 56')
for c in CR:
    po=pairs(own,[c]); pf=pairs(first,[c])
    print(f'{c[:3].upper()}  {round(100*sum(x==y for x,y in po)/len(po))}  |  {round(100*sum(x==y for x,y in pf)/len(pf))}')
print('== C01 / C09 examples (first 56)')
for c in ['c01_overall_legal_correctness','c09_reasoning_coherence']:
    hc=collections.Counter(H[k][c+'_label'] for k in first); jc=collections.Counter(J[k][c+'_label'] for k in first)
    p=pairs(first,[c]); po=sum(x==y for x,y in p)/len(p)
    pe=sum(hc[l]*jc[l] for l in set(hc)|set(jc))/56/56
    print(c[:3], 'reviewer',dict(hc),'judge',dict(jc),f'obs {sum(x==y for x,y in p)}/56 {100*po:.1f}% exp {100*pe:.1f}% kappa {(po-pe)/(1-pe):.2f}')
print('== own RAG source labels'); 
for c in SRC: print(c[:3],'judge',dict(collections.Counter(J[k][c+'_label'] for k in own)),'reviewer',dict(collections.Counter(H[k][c+'_label'] for k in own)))
print('== legally correct and complete per judge? (C01&C02 met) own RAG judge:',sum(1 for k in own if J[k]['c01_overall_legal_correctness_label']=='met' and J[k]['c02_required_elements_complete_label']=='met'))


def write_subset_csv(path):
    """Agreement, kappa, stability and direction per criterion for all_70, earlier_56 and self_retrieval_14."""
    import csv as _csv
    subsets = {'all_70': first + own, 'earlier_56': first, 'self_retrieval_14': own}
    rows = []
    for sname, keys in subsets.items():
        for cname, crit in [(c, [c]) for c in CR] + [('seven_judgement_criteria', JUDG), ('three_source_criteria', SRC), ('all_ten_criteria', CR)]:
            p = pairs(keys, crit)
            same = sum(x == y for x, y in p)
            stricter = sum(1 for x, y in p if x != y and y == 'not_met')
            lenient = sum(1 for x, y in p if x != y and y != 'not_met')
            stable = ''
            if len(crit) == 1:
                stable = sum(1 for k in keys if len({R[i][k][crit[0] + '_label'] for i in (1, 2, 3)}) == 1)
            rows.append({'subset': sname, 'criterion': cname, 'decisions': len(p), 'same_label': same,
                         'agreement_pct': round(100 * same / len(p), 1), 'cohen_kappa': round(kappa(p), 2),
                         'stable_in_3_runs': stable, 'judge_stricter': stricter, 'judge_more_lenient': lenient})
    with open(path, 'w', newline='', encoding='utf-8') as h:
        w = _csv.DictWriter(h, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print('wrote', path)


if len(sys.argv) > 2 and sys.argv[2] == '--csv':
    write_subset_csv(sys.argv[3])

# Added 16 November 2026: the main result under each assessor (Section 6.7, robustness to the reviewer).
print('== correct and complete (C01 and C02 Met): legal reviewer | LLM judge run 1 | both | judge in all three runs')
def cc(r): return r['c01_overall_legal_correctness_label']=='met' and r['c02_required_elements_complete_label']=='met'
for name,keys in (('without source',cb),('with correct source',gc),('own RAG system',own)):
    print(f"{name:20s} n={len(keys)}  reviewer {sum(cc(H[k]) for k in keys)}  judge {sum(cc(J[k]) for k in keys)}  both {sum(cc(H[k]) and cc(J[k]) for k in keys)}  judge x3 {sum(all(cc(R[i][k]) for i in (1,2,3)) for k in keys)}")
