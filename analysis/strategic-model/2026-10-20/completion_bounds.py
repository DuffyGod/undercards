"""Partial identification of eventual outcomes from saved finite rollouts.

An unfinished rollout is neither a win nor a calibrated leaf value. Bound its
completion instead. This is a new read-only analysis, not another simulation.
"""
from pathlib import Path
import argparse,csv,json,subprocess
import numpy as np
from scipy.stats import beta
from policy_game import solve
from run import HERE,ROOT,ROWS,COLS


def lower_binomial(successes,n,alpha):
    # Exact one-sided Clopper-Pearson, not a normal approximation at 0/1.
    return 0. if successes==0 else float(beta.ppf(alpha,successes,n-successes+1))


def empirical_envelope(win,loss):
    win,loss=np.asarray(win,dtype=float),np.asarray(loss,dtype=float)
    if win.shape!=loss.shape or win.ndim!=2 or np.any(win<0) or np.any(loss<0) or np.any(win+loss>1+1e-10):
        raise ValueError('Matching valid terminal win/loss matrices required')
    return [solve(win)['value'],solve(1-loss)['value']]


def derive(path):
    m=json.loads((path/'manifest.json').read_text())
    if m['status']!='complete':raise ValueError('Only complete frozen inputs')
    n=len(m['test_seeds']);columns=[0,1,2]
    with (path/'derived/cells.csv').open() as f:cells=list(csv.DictReader(f))
    findings=[]
    # Each world uses a simultaneous95% box over ALL frozen rows, timing
    # columns and TWO rates (win/loss). Bonferroni does not require independent
    # cells; only independently generated evaluation seeds for each cell.
    alpha=.05/(len(ROWS)*len(columns)*2)
    for world in m['worlds']:
        selected=[c for c in cells if c['world']==world]
        idx={(c['structure'],c['row_policy'],c['column']):c for c in selected}
        win=np.zeros((len(ROWS),3));loss=win.copy();lo=win.copy();hi=win.copy()
        for i,(structure,p) in enumerate(ROWS):
            for j in columns:
                c=idx[structure,p.name,COLS[j].name]
                w,l=float(c['won']),float(c['lost']);kw,kl=round(w*n),round(l*n)
                if abs(w*n-kw)>1e-8 or abs(l*n-kl)>1e-8:raise ValueError('Only individual row/column Bernoulli rates, not mixed rates')
                win[i,j]=w;loss[i,j]=l
                lo[i,j]=lower_binomial(kw,n,alpha)
                hi[i,j]=1-lower_binomial(kl,n,alpha)
        empirical=empirical_envelope(win,loss)
        lower_confidence=solve(lo);upper_confidence=solve(hi)
        pure_lo=lo.min(axis=1);pure_hi=hi.min(axis=1)
        pure_empirical_lo=win.min(axis=1);pure_empirical_hi=(1-loss).min(axis=1)
        empirical_retained=int(np.sum(pure_empirical_hi>=pure_empirical_lo.max()))
        best_pure_lower=float(pure_lo.max())
        admissible=[i for i in range(len(ROWS)) if pure_hi[i]>=best_pure_lower]
        findings.append(dict(world=world,
            empirical_completion_value_interval=empirical,
            chance_and_completion_value_interval=[lower_confidence['value'],upper_confidence['value']],
            confidence_scope='Per-world simultaneous95% one-sided exact-binomial boxes for all frozen row/column win and loss rates; includes arbitrary unfinished completions. Does NOT cover wrong game abstraction or omitted policy classes.',
            pure_policies_not_excluded=len(admissible),total_pure_policies=len(ROWS),
            empirical_only_pure_policies_not_excluded=empirical_retained,
            uncertainty_separation='Empirical-only retains unknown completion, but no sampling box. The larger confidence-retained set includes both completion and finite-sample uncertainty.',
            pure_policy_bounds=[dict(row=i,structure=ROWS[i][0],policy=ROWS[i][1].name,
                worst_response_win_interval=[float(pure_lo[i]),float(pure_hi[i])],not_excluded=i in admissible) for i in range(len(ROWS))],
            rule='A pure policy is excluded only if its upper worst-response win bound is below another pure policy lower bound. Retention is uncertainty, not equivalence or strength.',
            interpretation='Finite policy-pool minimax eventual-win envelope, not the deadline-life objective and not real-game win rates. Unknown continuation is adversarial for lower and favorable for upper; this is deliberately an outer bound.'))
    analysis_commit=subprocess.check_output(['git','log','-1','--format=%H','--',str(HERE/'completion_bounds.py')],cwd=ROOT,text=True).strip()
    result=dict(source_commit=m['source_commit'],analysis_source_commit=analysis_commit,new_simulations=0,findings=findings,
        method_revision='Keep deadline goals explicit. Refuse unique eventual-strength rankings when stochastic/unfinished intervals overlap; do not substitute F/J or fit one arbitrary continuation price.',
        assumptions=['Saved abstract rules and evaluation seeds', 'Declared finite row/timing-response pools',
            'Terminal outcomes stay terminal; unfinished outcomes only known to lie in[0,1]',
            'Per-world rate confidence; no external model-validity claim'])
    (path/'derived/completion-bounds.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    for f in findings:print(json.dumps({k:f[k] for k in ('world','empirical_completion_value_interval','chance_and_completion_value_interval','pure_policies_not_excluded')}))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--experiment',type=Path,default=HERE/'experiment-v01')
    derive(p.parse_args().experiment)
