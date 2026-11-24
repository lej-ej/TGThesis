import sys, pandas as pd, numpy as np
d=pd.read_csv(sys.argv[1])
d['Period Ending']=pd.to_datetime(d['Period Ending'])
d=d[d['Legal Process']!='Preservation Requests'].copy()
d['req']=d['User Data Requests'].fillna(0)
d['w']=d['req']*d['Percentage disclosed']
g=d.groupby(['Country/Region','Period Ending']).apply(lambda x: pd.Series({
  'requests':x['req'].sum(),'accounts':x['Accounts'].sum(),
  'disclosed_pct': x['w'].sum()/x.loc[x['Percentage disclosed'].notna(),'req'].sum() if x.loc[x['Percentage disclosed'].notna(),'req'].sum()>0 else np.nan}), include_groups=False).reset_index()
g.columns=['country','period','requests','accounts','disclosed_pct']
g.to_csv(sys.argv[2],index=False)
for c in ['United States','Brazil','Hong Kong','India','France','Germany','Israel','Russia','Chile','Colombia']:
    s=g[g.country==c]
    print('\n##',c); print(s[s.period>='2016'][['period','requests','accounts','disclosed_pct']].to_string(index=False))
