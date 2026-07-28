#!/usr/bin/env python3
"""
每日净值自动更新脚本（GitHub Actions 运行）
更新内容：最新净值/日涨跌/区间收益/今年来/净值走势序列/FOF子基金因子收益
不更新：重仓持仓、季报观点、估值模型系数（季度级数据）
"""
import json, re, sys, time, datetime
import requests

DATA_FILE = 'data.js'
# 净值查询代码映射（519703为后端份额，净值同前端519702）
NAV_CODE = {'519753': '519753', '017850': '017850', '024439': '024439',
            '519703': '519702', '026355': '026355', '026604': '026604'}
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
           'Referer': 'https://fundf10.eastmoney.com/'}


def fetch_nav_akshare(code):
    """主源：akshare（东方财富）"""
    import akshare as ak
    df = ak.fund_open_fund_info_em(symbol=code, indicator='单位净值走势')
    out = []
    for _, r in df.iterrows():
        g = r.get('日增长率')
        out.append({'date': str(r['净值日期'])[:10], 'nav': float(r['单位净值']),
                    'growth': None if g != g else float(g)})
    return out


def fetch_nav_pingzhong(code):
    """备用源1：天天基金 pingzhongdata js"""
    r = requests.get(f'https://fund.eastmoney.com/pingzhongdata/{code}.js', headers=HEADERS, timeout=20)
    m = re.search(r'var Data_netWorthTrend\s*=\s*(\[.*?\]);', r.text)
    arr = json.loads(m.group(1))
    out = []
    prev = None
    for it in arr:
        d = datetime.datetime.fromtimestamp(it['x'] / 1000).strftime('%Y-%m-%d')
        v = float(it['y'])
        g = it.get('unitMoney')
        if g in (None, ''):
            g = None if prev is None else round((v / prev - 1) * 100, 4)
        else:
            g = float(g)
        out.append({'date': d, 'nav': v, 'growth': g})
        prev = v
    return out


def fetch_nav_lsjz(code):
    """备用源2：天天基金 f10 历史净值接口"""
    out = []
    for page in (1, 2, 3):
        r = requests.get(f'https://api.fund.eastmoney.com/f10/lsjz?fundCode={code}&pageIndex={page}&pageSize=40',
                         headers=HEADERS, timeout=20)
        rows = (r.json().get('Data') or {}).get('LSJZList') or []
        if not rows:
            break
        for it in rows:
            v = it.get('DWJZ')
            if not v:
                continue
            g = it.get('JZZZL')
            out.append({'date': it['FSRQ'], 'nav': float(v),
                        'growth': None if g in (None, '') else float(g)})
        if len(rows) < 40:
            break
    out.sort(key=lambda x: x['date'])
    return out


def fetch_nav(code):
    errs = []
    for name, fn in [('akshare', fetch_nav_akshare), ('pingzhong', fetch_nav_pingzhong), ('lsjz', fetch_nav_lsjz)]:
        try:
            data = fn(code)
            if data and len(data) >= 5:
                print(f'  [{name}] {code}: {len(data)}条, 最新 {data[-1]["date"]} = {data[-1]["nav"]}')
                return data
            errs.append(f'{name}:数据不足')
        except Exception as e:
            errs.append(f'{name}:{e}')
            time.sleep(2)
    print(f'  !! {code} 全部源失败: {errs}')
    return None


def period_ret(nav_list, days):
    if len(nav_list) < days + 1:
        return None
    return round((nav_list[-1]['nav'] / nav_list[-days - 1]['nav'] - 1) * 100, 2)


def ytd_ret(nav_list, this_year):
    prev = None
    for it in nav_list:
        if it['date'][:4] < this_year:
            prev = it
        else:
            break
    base = prev if prev else nav_list[0]
    return round((nav_list[-1]['nav'] / base['nav'] - 1) * 100, 2)


def main():
    raw = open(DATA_FILE, encoding='utf-8').read()
    data = json.loads(raw.replace('window.FUND_DATA = ', '').rstrip().rstrip(';'))
    this_year = str(datetime.datetime.now().year)
    changed = False

    for f in data['funds']:
        code = f['code']
        nav_code = NAV_CODE.get(code, code)
        print(f'更新 {code} {f["name"]} ...')
        nav_list = fetch_nav(nav_code)
        if not nav_list:
            print(f'  跳过（保留原数据）')
            continue
        latest, prev = nav_list[-1], nav_list[-2]
        if latest['date'] == f['nav_date'] and abs(latest['nav'] - f['nav']) < 1e-9:
            print(f'  净值未变（{latest["date"]}），仍刷新区间收益')
        else:
            changed = True
        day_g = latest['growth']
        if day_g is None:
            day_g = round((latest['nav'] / prev['nav'] - 1) * 100, 2)
        f['nav'] = latest['nav']
        f['nav_date'] = latest['date']
        f['day_growth'] = day_g
        f['ret_1w'] = period_ret(nav_list, 5)
        f['ret_1m'] = period_ret(nav_list, 21)
        f['ret_3m'] = period_ret(nav_list, 63)
        f['ret_ytd'] = ytd_ret(nav_list, this_year)
        f['nav_series'] = [{'d': x['date'], 'v': x['nav']} for x in nav_list[-60:]]

        # FOF 子基金因子：更新最近一日收益
        for fa in f.get('model', {}).get('factors', []):
            st = fa.get('static')
            if st and st.get('code'):
                sub = fetch_nav(st['code'])
                if sub and len(sub) >= 2:
                    g = sub[-1]['growth']
                    if g is None:
                        g = round((sub[-1]['nav'] / sub[-2]['nav'] - 1) * 100, 4)
                    if sub[-1]['date'] != st.get('date'):
                        changed = True
                    st['date'], st['ret'] = sub[-1]['date'], round(g, 4)
                time.sleep(0.3)

    today = datetime.datetime.now().strftime('%Y-%m-%d')
    if data.get('updated') != today:
        data['updated'] = today
        changed = True

    js = 'window.FUND_DATA = ' + json.dumps(data, ensure_ascii=False) + ';'
    open(DATA_FILE, 'w', encoding='utf-8').write(js)
    print(f'\n完成。数据是否有变化: {changed}')
    open('/tmp/nav_changed', 'w').write('1' if changed else '0')


if __name__ == '__main__':
    main()
