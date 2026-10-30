"""Standalone figure from saved paired comparisons, without simulations."""
from pathlib import Path
import os,json,csv
os.environ.setdefault('MPLCONFIGDIR','/tmp/undercards-mpl-20261030')
os.environ.setdefault('XDG_CACHE_HOME','/tmp/undercards-cache-20261030')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent


def main():
    dest=HERE/'experiment-v01';s=json.loads((dest/'summary.json').read_text())
    worlds=list(json.loads((dest/'manifest.json').read_text())['worlds'])
    columns=['trade_hold_two','face_hold_two','frontier_defender']
    conditions=[(w,h) for w in worlds for h in ('wide','anchor')]
    data=[];arrays=[]
    for card in ('Candy Dish','Aaron'):
        a=np.zeros((len(conditions),len(columns)))
        for i,(w,h) in enumerate(conditions):
            for j,c in enumerate(columns):
                r=next(r for r in s['comparisons'] if r['world']==w and r['structure']==h and r['a']==card and r['b']=='Rock Pet' and r['column']==c)
                v=r['win_difference'];a[i,j]=v['mean']*100
                data.append(dict(candidate=card,world=w,host=h,column=c,difference_pp=a[i,j],low_pp=100*v['approx95'][0],high_pp=100*v['approx95'][1]))
        arrays.append(a)
    limit=max(20,max(abs(a).max() for a in arrays))
    fig,axes=plt.subplots(1,2,figsize=(12,7),sharey=True,constrained_layout=True)
    labels=[w.replace('_integrity_',' I ').replace('_kindness_',' K ').replace('seat0','first').replace('seat1','second')+' / '+h for w,h in conditions]
    for ax,a,card in zip(axes,arrays,('Candy Dish','Aaron')):
        im=ax.imshow(a,cmap='BrBG',vmin=-limit,vmax=limit,aspect='auto')
        ax.set_title(card+' minus Rock Pet');ax.set_yticks(range(len(labels)),labels)
        ax.set_xticks(range(3),['Trade / hold2','Face / hold2','Coordinated'])
        for i in range(len(labels)):
            for j in range(3):ax.text(j,i,f'{a[i,j]:+.1f}',ha='center',va='center',fontsize=9,color='white' if abs(a[i,j])>.65*limit else '#17252a')
    fig.colorbar(im,ax=axes,label='Final win difference, percentage points',shrink=.65)
    fig.suptitle('Real ordinary bodies in abstract hosts: rankings depend on the opponent\nFrozen policy fits;128 paired deals; not actual Undercards win rates',fontsize=13)
    fig.savefig(dest/'body-comparison.png',dpi=180);svg=dest/'body-comparison.svg';fig.savefig(svg)
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
    with (dest/'figure-data.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(data[0]),lineterminator='\n');w.writeheader();w.writerows(data)


if __name__=='__main__':main()
