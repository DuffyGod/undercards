"""Export comparable conditional outcome planes; no aggregate ladder score."""
import os
os.environ.setdefault('MPLCONFIGDIR','/tmp/undercards-joint-mpl')
os.environ.setdefault('XDG_CACHE_HOME','/tmp/undercards-joint-cache')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from analyze import *

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=HERE/'derived');args=p.parse_args()
    summaries=[]
    for stage in ('tactics','extension','stress','stress_extension'):
        _,gs=load(HERE/stage);summaries.extend((g,summarize(rs)) for g,rs in gs)
    colors=dict(small_draw='#d28b00',middle_draw='#168075',heavy='#644ba0',small_anchor='#2a7dc6',small_reach='#ca4165')
    markers=dict(small_draw='o',middle_draw='s',heavy='^',small_anchor='D',small_reach='*')
    for name,opponents in (('balanced',('mid','large_reply')),('pressure',('pressure_mid','pressure_large'))):
        fig,axs=plt.subplots(2,2,figsize=(10,8),sharex=True,sharey=True)
        for ax,(opponent,seat) in zip(axs.flat,[(o,s) for o in opponents for s in (0,1)]):
            for g,m in summaries:
                if g['opponent']!=opponent or g['seat']!=seat:continue
                c=g['composition'];x=m['dead']['mean'];y=m['killed']['mean']
                xi=m['dead']['wilson95'];yi=m['killed']['wilson95']
                ax.errorbar(x*100,y*100,xerr=[[100*(x-xi[0])],[100*(xi[1]-x)]],yerr=[[100*(y-yi[0])],[100*(yi[1]-y)]],color=colors[c],marker=markers[c],ms=9 if c=='small_reach' else 6,capsize=2,alpha=.85,label=c)
            ax.set_title(f'{opponent} / {"first" if seat==0 else "second"}');ax.grid(alpha=.2);ax.set_xlim(0,65);ax.set_ylim(0,102)
        for ax in axs[-1,:]:ax.set_xlabel('Dead by turn 8 (%) - lower is better')
        for ax in axs[:,0]:ax.set_ylabel('Opponent killed by turn 8 (%)')
        axs[0,0].legend(fontsize=8,loc='lower right');fig.suptitle('Kindness / balanced own policy / public tactics both sides\n128 paired shuffles per point; Wilson 95%; restricted compositions, not ladder win rates',fontsize=11)
        fig.tight_layout();args.output.mkdir(exist_ok=True)
        for ext in ('svg','png'):fig.savefig(args.output/f'outcome-plane-{name}.{ext}',dpi=170)
        plt.close(fig)
if __name__=='__main__':main()
