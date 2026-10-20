"""Independent saved-polygon audit. Standard library; no producer imports."""
import argparse,gzip,json
from pathlib import Path


def inside(x,y,polygon):
    hit=False
    for (a,b),(c,d) in zip(polygon,polygon[1:]+polygon[:1]):
        cross=(x-a)*(d-b)-(y-b)*(c-a)
        if abs(cross)<1e-8 and min(a,c)-1e-8<=x<=max(a,c)+1e-8 and min(b,d)-1e-8<=y<=max(b,d)+1e-8:
            return True
        if (b>y)!=(d>y) and x<(c-a)*(y-b)/(d-b)+a:hit=not hit
    return hit


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():p.error('Do not overwrite an audit record')
    with gzip.open(args.source/'packages.json.gz','rt',encoding='utf-8') as f:data=json.load(f)
    vertices=points=0;failures=[]
    for case,record in data.items():
        for name,setting in record['settings'].items():
            rows={tuple(r['package']):r for r in setting['packages'] if r['feasible']}
            def value(r,x,y):return r['intercept']-x*r['net_paid']-y*r['cards_used']
            for region in setting['regions']:
                row=rows[tuple(region['package'])]
                for x,y in region['price_polygon']:
                    vertices+=1
                    gap=value(row,x,y)-max(value(r,x,y) for r in rows.values())
                    if gap< -1e-7:failures.append(dict(case=case,setting=name,kind='invalid_vertex',gap=gap))
            for x in (0.,.25,.5,.75,1.):
                for y in (0.,.5,1.,2.,3.):
                    points+=1
                    if not rows:continue
                    best=max(value(r,x,y) for r in rows.values())
                    if not any(abs(value(rows[tuple(region['package'])],x,y)-best)<1e-7 and
                               inside(x,y,region['price_polygon']) for region in setting['regions']):
                        failures.append(dict(case=case,setting=name,kind='coverage_gap',point=[x,y]))
    out=dict(source=str(args.source),vertices_checked=vertices,price_points_checked=points,
             failures=failures,physical_search_executed=False,
             limitations='Floating-point polygon consistency only; finite coverage grid, not a formal clipping proof or real-world price calibration')
    args.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(vertices=vertices,points=points,failures=len(failures))))
    if failures:raise SystemExit(1)


if __name__=='__main__':main()
