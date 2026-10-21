"""Export a stand-alone figure of frozen-prefix vs completed outcomes."""
import json,csv,os
os.environ.setdefault('MPLCONFIGDIR','/tmp/undercards-mpl')
os.environ.setdefault('XDG_CACHE_HOME','/tmp/undercards-cache')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from run import HERE


def main():
    path=HERE/'objective-validation-v01'
    prefix={w['world']:w for w in json.loads((path/'summary.json').read_text())['results']}
    final={w['world']:w for w in json.loads((path/'continuation/summary.json').read_text())['results']}
    dest=path/'figures';dest.mkdir(exist_ok=True)
    names=['sweep_integrity_seat0','focus_integrity_seat1']
    goals=['life','win_by_deadline','survive_deadline'];rows=[]
    fig,axes=plt.subplots(1,2,figsize=(12,5),sharex=True,constrained_layout=True)
    colors=['#237b55','#b74b4b','#c5cbd0']
    for ax,name in zip(axes,names):
        values=[];labels=[]
        for goal,label in zip(goals,['HP objective','Win by turn12','Alive at turn12']):
            early=prefix[name]['goals'][goal]['against_timing_policies'][1]
            late=final[name]['goals'][goal][1]
            for phase,data in [('T12',early),('Final',late)]:
                v=[data['win'],data['loss'],data['unfinished']];values.append(v);labels.append(f'{label}: {phase}')
                rows.append(dict(world=name,objective=goal,phase=phase,win=v[0],loss=v[1],unfinished=v[2]))
        for y,v in enumerate(values):
            start=0
            for size,color in zip(v,colors):
                ax.barh(y,size,left=start,color=color,height=.72)
                if size>=.08:ax.text(start+size/2,y,f'{size:.0%}',ha='center',va='center',color='white' if color!=colors[2] else '#30343a',fontsize=9)
                start+=size
        ax.set_yticks(range(len(labels)),labels);ax.invert_yaxis();ax.set_xlim(0,1)
        ax.set_title(name.replace('_',' ')+' vs hold two',fontsize=11)
        ax.set_xlabel('Outcome share; same frozen mixture and paired128 seeds')
        ax.set_xticks([0,.25,.5,.75,1],['0%','25%','50%','75%','100%'])
    handles=[plt.Rectangle((0,0),1,1,color=c) for c in colors]
    fig.legend(handles,['Won','Lost','Unfinished'],loc='outside lower center',ncols=3)
    fig.suptitle('A deadline is not the end of the game — abstract role model',fontsize=14)
    fig.savefig(dest/'deadline-vs-final.svg');fig.savefig(dest/'deadline-vs-final.png',dpi=170)
    svg=dest/'deadline-vs-final.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
    with (dest/'figure-data.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)


if __name__=='__main__':main()
