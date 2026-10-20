"""Read earlier shared cutoffs from saved half-turn snapshots, no new rollouts."""
from analyze import *

def at_turn(row,turn):
    if not 1<=turn<=8:raise ValueError('Saved study covers turns 1..8')
    candidates=[s for s in row['snapshots'] if s['turn']<=turn]
    if not candidates:raise ValueError('No saved cutoff')
    s=candidates[-1];p=s['players'][row['seat']];e=s['players'][1-row['seat']]
    return dict(killed=e['hp']<=0,dead=p['hp']<=0,hp=max(0,p['hp']),opponent_hp=max(0,e['hp']),
                pressure_15=e['hp']<=15,hand=p['hand'],cash=p['cash'],field_attack=p['attack'],
                observed_through_turn=s['turn'],observed_actor=s['actor'])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directories',nargs='+',type=Path)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args();rows=[]
    for directory in args.directories:
        _,groups=load(directory)
        for g,rs in groups:
            for turn in (2,4,6,8):
                ms=[at_turn(r,turn) for r in rs]
                rows.append(dict(stage=directory.name,**g,turn=turn,n=len(rs),**{k:mean(x[k] for x in ms) for k in ('killed','dead','hp','opponent_hp','pressure_15','hand','cash','field_attack')}))
    with args.output.open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print(json.dumps(dict(rows=len(rows),interpretation='Saved earlier cutoffs; terminal deaths absorb. Seats separate; last deployment exposure differs.')))
if __name__=='__main__':main()
