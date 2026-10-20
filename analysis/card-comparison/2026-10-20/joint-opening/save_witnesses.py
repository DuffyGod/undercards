"""Add selected complete action evidence to new saved rollouts.

Only selected new-study seeds replay, to supply action logs missing in summary
records. Endpoints/snapshots must match frozen records exactly. Not new samples.
"""
from analyze import load,HERE
from run_study import trial
from model import CARDS,ROOT
from pathlib import Path
import json,subprocess

def main():
    out=HERE/'witnesses'
    if out.exists():raise ValueError('Refusing overwrite')
    out.mkdir();cache={}
    def group(stage,**kw):
        if stage not in cache:cache[stage]=load(HERE/stage)[1]
        hits=[(g,rows) for g,rows in cache[stage] if all(g[k]==v for k,v in kw.items())]
        if len(hits)!=1:raise ValueError('Ambiguous witness group')
        return hits[0]
    specs=[]
    g,reach=group('extension',composition='small_reach',opponent='large_reply',seat=1)
    b,base=group('tactics',composition='small_draw',opponent='large_reply',seat=1)
    ref={r['seed']:r for r in base}
    r=next(r for r in reach if r['players'][1]['killed'] and ref[r['seed']]['players'][1]['dead'])
    specs += [('reach-success','extension',g,r),('same-shuffle-small-fails','tactics',b,ref[r['seed']])]
    g,anchor=group('extension',composition='small_anchor',opponent='large_reply',seat=0)
    b,base=group('tactics',composition='small_draw',opponent='large_reply',seat=0)
    ref={r['seed']:r for r in base}
    r=next(r for r in anchor if r['players'][0]['dead'] and not ref[r['seed']]['players'][0]['dead'])
    specs += [('bench-is-not-automatic-fix','extension',g,r),('same-shuffle-small-baseline','tactics',b,ref[r['seed']])]
    g,rows=group('main',composition='small_draw',policy='pressure',soul='KINDNESS',opponent='large_reply',seat=0)
    r=next(r for r in rows if r['players'][0]['dead'] and r['players'][0]['damage']>=25)
    specs += [('face-damage-without-finish','main',g,r)]
    g,rows=group('tactics',composition='heavy',opponent='mid',seat=0)
    r=next(r for r in rows if r['players'][0]['first_turn_no_opener'] and r['players'][0]['killed'])
    specs += [('no-opener-but-recovered','tactics',g,r)]
    g,rows=group('counterfactual',composition='middle_draw',policy='balanced',seat=1,intervention='extra_natural')
    r=next(r for r in rows if r['players'][1]['burned']>=5 and r['players'][1]['fatigue_damage']>0)
    specs += [('extra-draw-capacity-and-fatigue','counterfactual',g,r)]
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    index=[]
    for name,stage,g,r in specs:
        replay=trial(g,r['seed'],8,trace=True)
        if r['players']!=replay['players'] or r['snapshots']!=replay['snapshots']:
            raise ValueError(f'Replay differs: {name}; preserve and investigate')
        data=dict(purpose='Selected complete action witness; not an additional random sample',stage=stage,
                  saved_version=r['version'],replay_version=replay['version'],replay_source_commit=revision,
                  endpoint_and_snapshots_equal=True,group=g,**{'replay':replay})
        (out/f'{name}.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
        side=g['seat'];s=replay['players'][side];e=replay['players'][1-side]
        lines=[f'# {name}',f"\n{stage} / {g} / seed {r['seed']}。这是选定动作见证，不代表频率。",
               f"\n己方 P{side}，终点 HP {s['hp']}，敌 HP {s['opponent_hp']}；实际打脸 {s['damage']}，敌实际回复 {e['healed']}；烧牌 {s['burned']}。",
               '\n| 己回合 | 行动方 | 事件 |','| --- | --- | --- |']
        names={}
        for ev in replay['trace']:
            k=ev['kind'];who=ev.get('side',ev['turn_actor']);text=None
            if k=='draw':
                names[(who,ev['uid'])]=CARDS[ev['card']]['name']
                if ev['burned']:text=f"烧毁 {CARDS[ev['card']]['name']} ({ev['source']})"
            elif k=='play':text=f"出 {CARDS[ev['card']]['name']}，{ev['cost']}G"
            elif k=='attack':
                actor=names.get((who,ev['actor']),str(ev['actor']))
                target='hero' if ev['target']=='hero' else names.get((1-who,ev['target']),str(ev['target']))
                text=f'{actor} → {target}'
                if ev.get('monster_heal'):text+=f"；自身回复{ev['monster_heal']}"
            elif k=='fatigue':text=f"疲劳 {ev['damage']}"
            elif k=='heal' and ev['actual']:text=f"英雄回复 {ev['actual']}"
            elif k=='end':text=f"结束 HP {ev['hp']} / G {ev['cash']} / 手牌 {ev['hand']} / 格 {ev['slots']}"
            if text:lines.append(f"| {ev['turn']} | P{who} | {text} |")
        (out/f'{name}.md').write_text('\n'.join(lines)+'\n')
        index.append(dict(name=name,stage=stage,seed=r['seed'],group=g,endpoint_equal=True))
    (out/'index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(selected_replays=len(index),all_match=True)))
if __name__=='__main__':main()
