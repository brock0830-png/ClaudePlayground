import pandas as pd, numpy as np
F=pd.read_pickle('footprint_features.pkl'); SPLIT=pd.Timestamp('2024-01-01',tz='UTC')
F['t']=pd.to_datetime(F.t,utc=True); A=F[F.t<SPLIT]; B=F[F.t>=SPLIT]
print(f'signals with footprints: {len(F)} (2022-23: {len(A)}, 2024-26: {len(B)}); base net 2022-23 {100*A.net.mean():+.2f}%, 2024-26 {100*B.net.mean():+.2f}%')
def dmean(x): return x.groupby(x.t.dt.floor('D')).net.mean()
def diff_t(G,Bd):
    g,b=dmean(G),dmean(Bd); return (g.mean()-b.mean())/np.sqrt(g.var()/len(g)+b.var()/len(b))
rows=[]
for k,kind,good in [('F1_trapped','cont','high'),('F2_absorb','bin',1),('F3_thin','cont','low'),('F4_stacked','bin',1)]:
    if kind=='cont':
        q1,q2=A[k].quantile([1/3,2/3])
        g=lambda x: x[x[k]>q2] if good=='high' else x[x[k]<=q1]
        b=lambda x: x[x[k]<=q1] if good=='high' else x[x[k]>q2]
        desc=f'top vs bottom third (cutoffs {q1:.3g}/{q2:.3g})'
    else:
        g=lambda x: x[x[k]==1]; b=lambda x: x[x[k]==0]; desc='present vs absent'
    r=dict(feature=k,compare=desc)
    for lab,x in [('22-23',A),('24-26',B)]:
        G,Bd=g(x),b(x); r[f'{lab} good']=f'{100*G.net.mean():+.2f}% (n={len(G)})'; r[f'{lab} bad']=f'{100*Bd.net.mean():+.2f}%'
        r[f'{lab} diff']=round(100*(G.net.mean()-Bd.net.mean()),2)
    P=pd.concat([A,B]); r['pooled day-t']=round(diff_t(g(P),b(P)),2)
    r['PASS']=bool(r['22-23 diff']>0 and r['24-26 diff']>0 and r['pooled day-t']>=2.5)
    rows.append(r)
pd.set_option('display.width',250); print(pd.DataFrame(rows).to_string(index=False))
print('\nfeature prevalence:', {k:round(F[k].mean(),3) for k in ['F2_absorb','F4_stacked']})
