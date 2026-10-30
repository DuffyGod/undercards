"""Exact attack-only frontier; the endpoint preference is an explicit heuristic.

No card prices, hidden hands, draws, deck order or seed enter this module. It
enumerates attacks plus at most one currently held, affordable response. It
does not search deployments, draw outcomes, future enemy actions or full games.
"""
from functools import lru_cache


@lru_cache(maxsize=20000)
def frontier(own, enemy, response_kind='', packet=3):
    """Return unique (own HPs, enemy HPs, face damage, cast, plan) leaves.

    own entries are (attack, current HP, ready), enemy entries (attack, HP).
    Original tuple positions are stable action labels even after a death.
    Attacking face is always legal in this declared no-Taunt domain. Therefore
    stopping with unused positive attacks is weakly dominated at this horizon.
    """
    @lru_cache(maxsize=None)
    def walk(oh, eh, ready, spell):
        leaves={}
        def keep(a,b,damage,cast,plan):
            key=(a,b,damage,cast)
            if key not in leaves:leaves[key]=plan
        if not ready:
            keep(oh,eh,0,False,())
        seen_attackers=set()
        for i in ready:
            signature=(own[i][0],oh[i])
            if signature in seen_attackers:continue
            seen_attackers.add(signature)
            remainder=tuple(j for j in ready if j!=i)
            for a,b,d,s,p in walk(oh,eh,remainder,spell):
                keep(a,b,d+own[i][0],s,(('attack',i,-1),)+p)
            seen_targets=set()
            for j,h in enumerate(eh):
                if h<=0:continue
                signature=(enemy[j][0],h)
                if signature in seen_targets:continue
                seen_targets.add(signature)
                aa=list(oh);bb=list(eh)
                aa[i]=max(0,aa[i]-enemy[j][0]);bb[j]=max(0,bb[j]-own[i][0])
                for a,b,d,s,p in walk(tuple(aa),tuple(bb),remainder,spell):
                    keep(a,b,d,s,(('attack',i,j),)+p)
        if spell and any(h>0 for h in eh):
            bb=list(eh)
            if response_kind=='sweep':bb=[max(0,h-packet) for h in bb]
            else:
                j=max((j for j,h in enumerate(bb) if h>0),key=lambda j:(enemy[j][0],bb[j],-j))
                bb[j]=0
            for a,b,d,s,p in walk(oh,tuple(bb),ready,False):
                keep(a,b,d,True,(('response',-1,-1),)+p)
        return tuple((*k,p) for k,p in leaves.items())
    return walk(tuple(u[1] for u in own),tuple(u[1] for u in enemy),
                tuple(i for i,u in enumerate(own) if u[2] and u[1]>0),bool(response_kind))


def choose(own,enemy,hp,enemy_hp,mode='board',response_kind='',packet=3,end_heal=0):
    """Terminal/safety constrained heuristic, not a generic leaf value.

    Face damage first (race) and remaining attack differential first (board)
    are competing heuristics tested on final outcomes. Safety concerns only
    visible enemy bodies attacking face next; unseen reach/heal is not assumed
    absent in real games. A positive safety flag is not a full survival proof.
    """
    leaves=frontier(own,enemy,response_kind,packet)
    def score(leaf):
        oh,eh,damage,cast,plan=leaf
        ours=sum(u[0] for u,h in zip(own,oh) if h>0)
        theirs=sum(u[0] for u,h in zip(enemy,eh) if h>0)
        net=ours-theirs
        if damage>=enemy_hp:return (3,-int(cast),sum(h>0 for h in oh),damage,-len(plan))
        safe=theirs<min(30,hp+end_heal)
        priorities=(net,damage) if mode=='board' else (damage,net)
        # If no safe endpoint exists, lower incoming attack before chasing a
        # board/pressure preference. No fabricated HP-to-card exchange rate.
        return (2 if safe else 0,0 if safe else -theirs,*priorities,-int(cast),sum(oh),-len(plan))
    leaf=max(leaves,key=score)
    return leaf,score(leaf)
