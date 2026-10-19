"""Explicit demo only. Creates a NEW directory, never opens user Excel/Chrome."""
from pathlib import Path
from contextlib import closing
import argparse,json,sqlite3
import FastmarketsCollector_v3_4 as core
from report_model import build_context
from report_exports import export_reports
from smbs_rates import FXQuote,save_rates
from naver_markets import initialize_schema,parse_indicators,parse_capitalization

def create(folder):
    folder=Path(folder)
    folder.mkdir(parents=True,exist_ok=False)
    db=core.path_bundle(folder)['db']
    rows=[]
    for i,(code,description,unit,price) in enumerate([
        ('MB-LI-0029','탄산리튬 / 합성 예시','USD/kg','11.25'),
        ('MB-CO-0001','코발트 / 합성 예시','USD/lb','15.75'),
        ('MB-MN-0001','망간 / 합성 예시','USD/tonne','1250'),
        ('MB-BMS-0012','Black Mass / 합성 예시','% payable','68.5')]):
        rows.append(core.Price(code,'2026-10-16',None,price,None,None,unit,description,'synthetic','Actual','TEST / 합성 데이터','demo'+str(i)))
    core.save_sqlite(db,rows,[],{'widget_count':0,'found_symbols':[r.symbol for r in rows],'warnings':['TEST / 합성 데이터']})
    save_rates(db,[FXQuote('2026-10-16','USD','1400','-2',1,'SMBS'),FXQuote('2026-10-16','JPY','950','1',100,'SMBS')])
    fixtures=Path(__file__).parent/'fixtures'
    with closing(sqlite3.connect(db)) as cx,cx:
        initialize_schema(cx)
        for name,parse,table,columns in [
            ('naver_indicators_synthetic.html',parse_indicators,'market_indicators',__import__('naver_markets').INDICATOR_COLUMNS),
            ('naver_capitalization_synthetic.html',parse_capitalization,'equity_rank_snapshots',__import__('naver_markets').EQUITY_COLUMNS)]:
            for day in ('2026-10-15','2026-10-16'):
                html=(fixtures/name).read_text().replace('2026-10-19',day)
                for row in parse(html,captured_at='2026-10-19T08:30:00+09:00')['rows']:
                    if table=='market_indicators':
                        from decimal import Decimal
                        values={'KOSPI':'2600.25','KOSDAQ':'850.5','SP500':'5800.75','NASDAQ':'18500.5','US10Y':'4.15','KR10Y':'3.1','GOLD':'2700.5','WTI':'75.25'}
                        row['value']=str(Decimal(values[row['instrument_id']])-(Decimal('1') if day.endswith('15') else 0))
                        if row['instrument_id'] in ('US10Y','KR10Y'):row['unit']='%'
                    else:
                        row['market_cap']=str((20-(row['rank'] or 11))*10000)
                        detail=json.loads(row['raw_json']);detail['market_cap_unit']='억원';row['raw_json']=json.dumps(detail,ensure_ascii=False)
                    cx.execute('INSERT OR REPLACE INTO '+table+'('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',[row[c] for c in columns])
    result=export_reports(build_context(folder,synthetic=True),folder/'reports',include_excel=True)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('new_folder');a=p.parse_args();create(a.new_folder)
