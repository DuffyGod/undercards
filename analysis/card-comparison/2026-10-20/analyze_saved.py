"""Derive comparison thresholds/figures from frozen evidence, never combat."""
import argparse,gzip,json
from collections import Counter
from pathlib import Path
from compare_packages import compare
from package_model import HERE,score

PAIRS=[('two_aaron','guard/INTEGRITY/empty/keep1',[15,15],[38]),
       ('three_small','guard/INTEGRITY/empty/keep1',[1,187,602],[38]),
       ('spent_twelve','guard/INTEGRITY/empty/keep1',[15,15,602],[38]),
       ('mixed_after_attacks','guard/INTEGRITY/two_durable/keep1',[38,187],[15,15,602])]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results',type=Path,default=HERE/'arrival-results')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--plot',action='store_true')
    args=p.parse_args()
    if args.output.exists():p.error('Use a new output directory')
    args.output.mkdir(parents=True)
    with gzip.open(args.results/'packages.json.gz','rt',encoding='utf-8') as f:data=json.load(f)
    pairs=[]
    for label,case,left,right in PAIRS:
        result=compare(data[case]['settings'],left,right,.5,1.)
        roots=[-(r['coefficients'][0]+.5*r['coefficients'][1])/r['coefficients'][2]
               for r in result['planes']]
        pairs.append(dict(label=label,case=case,left=left,right=right,
                          hand_price_roots_at_cash_half=[min(roots),max(roots)],**result))
    winners=[]
    for case in ('guard/INTEGRITY/empty/keep1','guard/INTEGRITY/two_durable/keep1',
                 'guard/KINDNESS/one_large_hit/keep1'):
        for mu in (0.,1.,2.,3.):
            names=[]
            for setting in data[case]['settings'].values():
                valid=[r for r in setting['packages'] if r['feasible']]
                names.append(tuple(max(valid,key=lambda r:score(r,.5,mu))['package']))
            winners.append(dict(case=case,cash_price=.5,hand_price=mu,
                                 winners=[dict(package=list(k),settings=n) for k,n in Counter(names).items()],
                                 count_warning='Settings count is sensitivity coverage, not votes or probability'))
    (args.output/'findings.json').write_text(json.dumps(dict(pairs=pairs,winners=winners,
                   physical_search_executed=False),ensure_ascii=False,indent=2)+'\n')
    if args.plot:
        import os,tempfile
        os.environ.setdefault('MPLCONFIGDIR',tempfile.mkdtemp(prefix='undercards-mpl-'))
        os.environ.setdefault('XDG_CACHE_HOME',tempfile.mkdtemp(prefix='undercards-font-'))
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import numpy as np
        x=np.linspace(0,1,301)
        fig,axes=plt.subplots(1,2,figsize=(11,4.6),sharey=True)
        for ax,pair,title in zip(axes,(pairs[0],pairs[2]),('Two Aaron (10G, 2 cards)','Two Aaron + Rock Pet (12G, 3 cards)')):
            lines=np.array([-(p['coefficients'][0]+p['coefficients'][1]*x)/p['coefficients'][2]
                            for p in pair['planes']])
            low=lines.min(axis=0);high=lines.max(axis=0)
            central=next(p['coefficients'] for p in pair['planes'] if p['setting']=='central')
            center=-(central[0]+central[1]*x)/central[2]
            ax.fill_between(x,0,low,color='#2a9d8f',alpha=.65,label='Split weakly higher at all 9 settings')
            ax.fill_between(x,low,high,color='#9ca3af',alpha=.55,label='Price settings disagree')
            ax.fill_between(x,high,3,color='#6c5b9b',alpha=.6,label='RG1 weakly higher at all 9 settings')
            ax.plot(x,center,'--',color='#111827',linewidth=1,label='Central body scale')
            ax.set(xlim=(0,1),ylim=(0,3),xlabel='Cash opportunity price (lambda)',title=title+'\nvs RG1 (9G, 1 card)')
        axes[0].set_ylabel('Opportunity price per used hand card (rho)')
        handles,labels=axes[0].get_legend_handles_labels()
        fig.legend(handles,labels,loc='lower center',ncol=2,fontsize=8)
        fig.suptitle('Fixed 12G hand window, empty enemy board, INTEGRITY; heuristic assets')
        fig.tight_layout(rect=(0,.14,1,.93))
        fig.savefig(args.output/'resource-regions.svg')
        fig.savefig(args.output/'resource-regions.png',dpi=150)
        plt.close(fig)
    print(json.dumps(dict(pair_thresholds=len(pairs),winner_rows=len(winners),physical_search_executed=False)))


if __name__=='__main__':main()
