import sys, pandas as pd, numpy as np
g=pd.read_csv(sys.argv[1],parse_dates=['period'])
g=g.sort_values(['country','period'])
g['lr']=np.log(g.requests.replace(0,np.nan))
g['growth']=g.groupby('country').lr.diff(2)
# expected growth = mean growth over prior 6 periods; disclosure baseline = mean of prior 2
g['exp_growth']=g.groupby('country').growth.transform(lambda s: (s.shift(2)+s.shift(4)+s.shift(6))/3)
g['disc_base']=g.groupby('country').disclosed_pct.transform(lambda s: s.shift(2))
g['excess_pct']=(np.exp(g.growth-g.exp_growth)-1)*100
g['disc_change']=g.disclosed_pct-g.disc_base
g['acct_per_req']=g.accounts/g.requests
ev=[('United States','2020-06-30','COVID-19 onset'),('United States','2021-06-30','Jan. 6 Capitol attack'),
('Brazil','2023-06-30','Jan. 8 Brasília attacks'),('Israel','2021-06-30','May 2021 war & unrest'),
('Israel','2023-12-31','Oct. 7 attack & war'),('France','2023-12-31','2023 urban riots'),
('Hong Kong','2019-12-31','2019 protests'),('Chile','2019-12-31','2019 estallido social'),
('India','2021-06-30','Farmers\' protests / Delta wave'),('Colombia','2021-06-30','2021 national strike')]
rows=[]
for c,p,l in ev:
    r=g[(g.country==c)&(g.period==p)].iloc[0]
    rows.append(dict(country=c,period=p,event=l,requests=int(r.requests),excess_vs_trend_pct=round(r.excess_pct,1),disclosed=round(r.disclosed_pct,1),disc_change_pts=round(r.disc_change,1)))
E=pd.DataFrame(rows); print(E.to_string(index=False)); E.to_csv(sys.argv[2],index=False)
# COVID common shock: countries with >=500 requests in 2019H2
big=g[(g.period=='2019-12-31')&(g.requests>=500)].country
c=g[(g.period=='2020-06-30')&g.country.isin(big)].dropna(subset=['excess_pct','disc_change'])
print('\nCOVID 2020H1, n=',len(c),' median excess growth %:',round(c.excess_pct.median(),1),' share above trend:',round((c.excess_pct>0).mean(),2),' median disclosure change:',round(c.disc_change.median(),1),' share disclosure fell >2pts:',round((c.disc_change<-2).mean(),2))
print(c[['country','requests','excess_pct','disc_change']].round(1).sort_values('excess_pct').to_string(index=False))
# all large-country periods: correlation of excess growth and disclosure change
a=g[(g.requests>=500)&(g.period>='2014')].dropna(subset=['excess_pct','disc_change'])
a=a[np.isfinite(a.excess_pct)]
print('\nAll country-periods (>=500 req, 2014+): n=',len(a),' corr(excess growth, disclosure change)=',round(a.excess_pct.corr(a.disc_change),3))
spk=a[a.excess_pct>=25]; norm=a[a.excess_pct.abs()<10]
print(' spikes >=25% above trend n=',len(spk),' mean disc change',round(spk.disc_change.mean(),2),' median',round(spk.disc_change.median(),2))
print(' normal periods n=',len(norm),' mean disc change',round(norm.disc_change.mean(),2),' median',round(norm.disc_change.median(),2))
us=g[g.country=='United States']
print('\nUS acct/request 2019H2..2021H2:'); print(us[(us.period>='2019')&(us.period<='2022')][['period','requests','accounts','acct_per_req','excess_pct','disclosed_pct']].round(2).to_string(index=False))
# headline: US/global
glob=g.groupby('period')[['requests']].sum()
print('\nGlobal requests 2012H2',glob.loc['2012-12-31'].requests,' 2025H2',glob.loc['2025-12-31'].requests)
w=g.assign(wd=g.requests*g.disclosed_pct).groupby('period').apply(lambda x: x.wd.sum()/x.loc[x.disclosed_pct.notna(),'requests'].sum(),include_groups=False)
print('Global weighted disclosure: 2014H1',round(w['2014-06-30'],1),' 2019H2',round(w['2019-12-31'],1),' 2025H2',round(w['2025-12-31'],1))
g.to_csv(sys.argv[3],index=False)
