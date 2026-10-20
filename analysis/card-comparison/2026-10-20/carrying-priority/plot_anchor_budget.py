"""Optional budget diagram, no battle simulation."""
import os,tempfile
from pathlib import Path
from carry_math import natural_total


def main():
    os.environ.setdefault('MPLCONFIGDIR',tempfile.mkdtemp(prefix='carry-mpl-'))
    os.environ.setdefault('XDG_CACHE_HOME',tempfile.mkdtemp(prefix='carry-font-'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    base=Path(__file__).resolve().parent
    fig,axes=plt.subplots(1,2,figsize=(10,4),sharey=True)
    for ax,seat,title in zip(axes,('first','second'),('First player','Second player')):
        turns=[1,2,3,4,5];gold=[natural_total(t,seat) for t in turns]
        ax.plot(turns,gold,'o-',label='No prior expenditure')
        ax.plot(turns,[g-2 for g in gold],'s-',label='2G already invested')
        ax.axhline(5,color='#888',linestyle='--',linewidth=1)
        ax.axhline(9,color='#555',linestyle=':',linewidth=1)
        ax.text(5.08,5,'5G',va='center',fontsize=9);ax.text(5.08,9,'9G',va='center',fontsize=9)
        ax.set(title=title,xlabel='Own turn',xticks=turns,xlim=(.9,5.5),ylim=(0,20))
    axes[0].set_ylabel('Available natural gold before anchor')
    fig.suptitle('Bridge budget: when does an early 2G body delay the next anchor?')
    axes[0].legend(fontsize=8,loc='upper left');fig.tight_layout()
    fig.savefig(base/'anchor-budget.png',dpi=150);fig.savefig(base/'anchor-budget.svg')
    svg=base/'anchor-budget.svg';svg.write_text('\n'.join(l.rstrip() for l in svg.read_text().splitlines())+'\n')


if __name__=='__main__':main()
