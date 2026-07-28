#!/usr/bin/env python3
"""
交银基金重点产品 - 数据库中枢自动更新
每晚运行：拉净值/行情 -> 入SQLite(fund.db) -> 重训估值模型 -> 导出data.js -> 提交
全程纯Python，不依赖AI。仅刷新动态数据；基金基础信息/重仓/观点来自 funds_base.json
"""
import json, sqlite3, datetime, time, re, requests
import numpy as np

BASE = 'funds_base.json'
DB = 'fund.db'
OUT = 'data.js'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

# 指数中文名 -> 腾讯代码
IDX_TX = {'沪深300': 'sh000300', '创业板指': 'sz399006', '科创50': 'sh000688',
          '中证500': 'sh000905', '中证1000': 'sh000852', '上证指数': 'sh000001',
          '国债指数': 'sh000012', '科创100': 'sh000698'}
TRAIN_DAYS = 45
VAL_DAYS = 15


def tx_code(code):
    sym, mkt = code.split('.')
    if mkt == 'SH': return 'sh' + sym
    if mkt == 'SZ': return 'sz' + sym
    if mkt == 'HK': return 'hk' + sym.zfill(5)


# ---------- 行情拉取 ----------
def fetch_nav_akshare(code):
    import akshare as ak
    df = ak.fund_open_fund_info_em(symbol=code, indicator='单位净值走势')
    out = []
    for _, r in df.iterrows():
        g = r.get('日增长率')
        out.append({'date': str(r['净值日期'])[:10], 'nav': float(r['单位净值']),
                    'growth': None if g != g else float(g)})
    return out


def fetch_nav_backup(code):
    r = requests.get(f'https://api.fund.eastmoney.com/f10/lsjz?fundCode={code}&pageIndex=1&pageSize=65',
                     headers={**HEADERS, 'Referer': 'https://fundf10.eastmoney.com/'}, timeout=20)
    rows = (r.json().get('Data') or {}).get('LSJZList') or []
    out = []
    for it in rows:
        if not it.get('DWJZ'): continue
        g = it.get('JZZZL')
        out.append({'date': it['FSRQ'], 'nav': float(it['DWJZ']),
                    'growth': None if g in (None, '') else float(g)})
    out.sort(key=lambda x: x['date'])
    return out


def fetch_nav(code):
    errs = []
    for fn in (fetch_nav_akshare, fetch_nav_backup):
        try:
            d = fn(code)
            if d and len(d) >= 5:
                return d
            errs.append('data<5')
        except Exception as e:
            errs.append(str(e)[:40]); time.sleep(1.5)
    print(f'  !! 净值 {code} 失败: {errs}')
    return None


def tx_kline(symbol, start='2026-05-01', end='2026-07-31', n=70):
    """腾讯日K -> {date: pct}"""
    if symbol.startswith('hk'):
        url = f'https://web.ifzq.gtimg.cn/appstock/app/hkfqkline/get?param={symbol},day,{start},{end},{n},qfq'
    else:
        url = f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,{start},{end},{n},qfq'
    r = requests.get(url, headers=HEADERS, timeout=15)
    d = r.json()['data'][symbol]
    key = 'qfqday' if 'qfqday' in d else 'day'
    rows = d[key]
    closes = [(row[0], float(row[2])) for row in rows]
    ret = {}
    for i in range(1, len(closes)):
        ret[closes[i][0]] = round((closes[i][1] / closes[i - 1][1] - 1) * 100, 4)
    return ret


# ---------- 模型 ----------
def ridge_fit(X, y, lam):
    n, p = X.shape
    A = X.T @ X + lam * np.eye(p)
    A[0, 0] -= lam
    return np.linalg.solve(A, X.T @ y)


def build_matrix(factor_dicts, dates):
    cols = [[fd.get(d) for d in dates] for fd in factor_dicts]
    X, keep = [], []
    for i, d in enumerate(dates):
        r = [c[i] for c in cols]
        if all(v is not None for v in r):
            X.append([1.0] + r)
            keep.append(d)
    return np.array(X, dtype=float), keep


def train_models(factor_series, idx_series, fr, asset_weights):
    """factor_series: 重仓资产 {name:{date:ret}}; idx_series: 指数 {name:{date:ret}};
       fr: 基金收益 {date:ret}; asset_weights: {name: 占净值比例(0~1)}"""
    all_dates = sorted(fr.keys())[-(TRAIN_DAYS + 8):]
    models = {}
    idx_name = '国债指数' if asset_weights.get('__bond__') else '沪深300'
    # M1 披露权重
    if factor_series:
        total_w = sum(asset_weights.get(nm, 0) for nm in factor_series)
        betas = [asset_weights.get(nm, 0) for nm in factor_series]
        betas.append(max(0.0, 1 - total_w))
        fd = list(factor_series.values()) + [idx_series.get(idx_name, {})]
        X, keep = build_matrix(fd, all_dates)
        yy = np.array([fr[d] for d in keep])
        pred = X[:, 1:] @ np.array(betas)
        models['M1'] = {'factors': list(factor_series.keys()) + [idx_name], 'beta': [0.0] + betas,
                        'pred': dict(zip(keep, pred)), 'y': dict(zip(keep, yy))}

    # 岭回归通用
    def train_ridge(fds, names):
        X, keep = build_matrix(fds, all_dates)
        yy = np.array([fr[d] for d in keep])
        n = len(yy)
        if n < VAL_DAYS + 8: return None
        tr = n - VAL_DAYS
        best = None
        for lam in [0.05, 0.2, 1.0, 5.0, 20.0]:
            beta_tr = ridge_fit(X[:tr], yy[:tr], lam)
            m = np.mean(np.abs(yy[tr:] - X[tr:] @ beta_tr))
            if best is None or m < best[0]:
                best = (m, lam)
        lam = best[1]
        beta = ridge_fit(X, yy, lam)
        pred = X @ beta
        return {'factors': names, 'beta': beta.tolist(), 'pred': dict(zip(keep, pred)), 'y': dict(zip(keep, yy))}

    if factor_series:
        r2 = train_ridge(list(factor_series.values()), list(factor_series.keys()))
        if r2: models['M2'] = r2
        fds3 = list(factor_series.values()) + list(idx_series.values())
        r3 = train_ridge(fds3, list(factor_series.keys()) + list(idx_series.keys()))
        if r3: models['M3'] = r3
    r4 = train_ridge(list(idx_series.values()), list(idx_series.keys()))
    if r4: models['M4'] = r4
    # 选近15日 MAE 最小
    best_m, best_score = None, 1e9
    scores = {}
    for mk, mo in models.items():
        dates = sorted(mo['y'].keys())[-VAL_DAYS:]
        yv = [mo['y'][d] for d in dates]; pv = [mo['pred'][d] for d in dates]
        mae = np.mean(np.abs(np.array(yv) - np.array(pv)))
        rmse = np.sqrt(np.mean((np.array(yv) - np.array(pv)) ** 2))
        dir_acc = float(np.mean(np.sign(np.array(yv)) == np.sign(np.array(pv))) * 100)
        scores[mk] = {'mae': round(mae, 4), 'rmse': round(rmse, 4), 'dir_acc': round(dir_acc, 1)}
        if mae < best_score:
            best_score, best_m = mae, mk
    bm = models[best_m]
    dates15 = sorted(bm['y'].keys())[-VAL_DAYS:]
    compare = [{'date': d, 'actual': round(bm['y'][d], 3), 'est': round(bm['pred'][d], 3),
                'diff': round(bm['pred'][d] - bm['y'][d], 3)} for d in dates15]
    names = {'M1': '披露权重模型', 'M2': '重仓资产回归模型', 'M3': '重仓+指数增强模型', 'M4': '宽基指数模型'}
    return {'type': best_m, 'name': names[best_m], 'factors': bm['factors'],
            'beta': [round(b, 4) for b in bm['beta']], 'intercept': round(bm['beta'][0], 4),
            'val_mae': scores[best_m]['mae'], 'val_rmse': scores[best_m]['rmse'],
            'val_dir_acc': scores[best_m]['dir_acc'], 'compare15': compare, 'all_scores': scores}


def main():
    base = json.load(open(BASE, encoding='utf-8'))
    nav_code = base['nav_code']
    funds = base['funds']
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    conn = sqlite3.connect(DB)
    conn.execute('CREATE TABLE IF NOT EXISTS nav_daily(code TEXT,date TEXT,nav REAL,growth REAL,PRIMARY KEY(code,date))')
    conn.execute('CREATE TABLE IF NOT EXISTS factor_daily(code TEXT,date TEXT,ret REAL,PRIMARY KEY(code,date))')

    def upsert_nav(code, rows):
        for r in rows:
            conn.execute('INSERT OR REPLACE INTO nav_daily VALUES(?,?,?,?)',
                         (code, r['date'], r['nav'], r['growth']))
        conn.commit()

    # 1) 净值
    nav_hist = {}
    for code, f in funds.items():
        print(f"净值 {code} {f['name']}")
        rows = fetch_nav(nav_code.get(code, code))
        if not rows:
            continue
        upsert_nav(code, rows)
        nav_hist[code] = {r['date']: r for r in rows}

    # 2) 因子：去重拉取
    stock_codes, idx_codes, sub_codes = set(), set(), set()
    for f in funds.values():
        for h in f['holdings']:
            stock_codes.add(h['code'])
        for h in f['fund_holdings']:
            sub_codes.add(h['code'])
        idx_codes |= set(IDX_TX.keys())  # 全部指数都拉，便于建模

    factor_hist = {}
    # 个股/指数(腾讯)
    for sc in sorted(stock_codes):
        try:
            ret = tx_kline(tx_code(sc))
            factor_hist[sc] = ret
            for d, v in ret.items():
                conn.execute('INSERT OR REPLACE INTO factor_daily VALUES(?,?,?)', (sc, d, v))
            time.sleep(0.05)
        except Exception as e:
            print(f'  个股 {sc} 失败 {e}')
    for nm in sorted(idx_codes):
        try:
            ret = tx_kline(IDX_TX[nm])
            factor_hist[nm] = ret
            for d, v in ret.items():
                conn.execute('INSERT OR REPLACE INTO factor_daily VALUES(?,?,?)', (nm, d, v))
            time.sleep(0.05)
        except Exception as e:
            print(f'  指数 {nm} 失败 {e}')
    # 子基金(akshare净值->收益)
    for sc in sorted(sub_codes):
        try:
            rows = fetch_nav(sc)
            if rows and len(rows) >= 2:
                ret = {}
                for i in range(1, len(rows)):
                    g = rows[i]['growth']
                    ret[rows[i]['date']] = round(g, 4) if g is not None else round(
                        (rows[i]['nav'] / rows[i - 1]['nav'] - 1) * 100, 4)
                factor_hist[sc] = ret
                for d, v in ret.items():
                    conn.execute('INSERT OR REPLACE INTO factor_daily VALUES(?,?,?)', (sc, d, v))
            time.sleep(0.3)
        except Exception as e:
            print(f'  子基金 {sc} 失败 {e}')
    conn.commit()

    # 3) 从库读历史，重训模型 + 组装
    cur = conn.cursor()
    def read_factor(code):
        return {d: v for (d, v) in cur.execute('SELECT date,ret FROM factor_daily WHERE code=?', (code,))}

    web = {'updated': today, 'funds': []}
    for code, f in funds.items():
        print(f"建模 {code} {f['name']}")
        nav_rows = cur.execute('SELECT date,nav,growth FROM nav_daily WHERE code=?', (code,)).fetchall()
        if not nav_rows:
            print('  跳过(无净值)'); continue
        nav_list = [{'date': d, 'nav': n, 'growth': g} for d, n, g in nav_rows]
        nav_list.sort(key=lambda x: x['date'])
        latest, prev = nav_list[-1], nav_list[-2]
        fr = {}
        for i in range(1, len(nav_list)):
            g = nav_list[i]['growth']
            fr[nav_list[i]['date']] = round(g, 4) if g is not None else round(
                (nav_list[i]['nav'] / nav_list[i - 1]['nav'] - 1) * 100, 4)

        # 因子集
        stk_series = {h['name']: read_factor(h['code']) for h in f['holdings']}
        sub_series = {h['name']: read_factor(h['code']) for h in f['fund_holdings']}
        asset_series = {**stk_series, **sub_series}
        is_bond = (not f['holdings']) or ('债券' in f['type']) or f['fund_holdings']
        idx_need = ['国债指数', '沪深300'] if is_bond else ['沪深300', '创业板指', '科创50', '中证500', '中证1000', '上证指数']
        idx_series = {nm: read_factor(nm) for nm in idx_need}
        asset_weights = {h['name']: h['weight'] / 100 for h in f['holdings']}
        for h in f['fund_holdings']:
            asset_weights[h['name']] = h['weight'] / 100
        asset_weights['__bond__'] = is_bond
        model = train_models(asset_series, idx_series, fr, asset_weights)

        # 组装 entry
        def period_ret(days):
            return round((latest['nav'] / nav_list[-days - 1]['nav'] - 1) * 100, 2) if len(nav_list) >= days + 1 else None
        prev_year = None
        for it in nav_list:
            if it['date'][:4] < str(datetime.datetime.now().year):
                prev_year = it
            else:
                break
        base_nav = prev_year if prev_year else nav_list[0]
        ytd = round((latest['nav'] / base_nav['nav'] - 1) * 100, 2)

        factors_out = []
        for i, fnm in enumerate(model['factors']):
            item = {'name': fnm, 'beta': model['beta'][i + 1]}
            # 找tx或static
            txc = None
            for h in f['holdings']:
                if h['name'] == fnm: txc = tx_code(h['code'])
            if fnm in IDX_TX: txc = IDX_TX[fnm]
            if txc:
                item['tx'] = txc
            else:
                for h in f['fund_holdings']:
                    if h['name'] == fnm and h['code'] in factor_hist:
                        sd = sorted(factor_hist[h['code']].keys())[-1]
                        item['static'] = {'code': h['code'], 'date': sd, 'ret': round(factor_hist[h['code']][sd], 4)}
            factors_out.append(item)

        web['funds'].append({
            'code': code, 'name': f['name'], 'full_name': f['full_name'], 'type': f['type'],
            'manager': f['manager'], 'risk': f.get('risk', ''), 'scale_yi': f['scale_yi'],
            'benchmark': f['benchmark'], 'nav': latest['nav'], 'nav_date': latest['date'],
            'day_growth': round(latest['growth'], 2) if latest['growth'] is not None else period_ret(1),
            'ret_1w': period_ret(5), 'ret_1m': period_ret(21), 'ret_3m': period_ret(63), 'ret_ytd': ytd,
            'nav_series': [{'d': x['date'], 'v': x['nav']} for x in nav_list[-60:]],
            'holdings': f['holdings'], 'fund_holdings': f['fund_holdings'], 'bond_holdings': f['bond_holdings'],
            'holding_period': f['holding_period'], 'note': f.get('note', ''),
            'tt_link': f['tt_link'], 'tt_f10': f['tt_f10'],
            'view_title': f['view_title'], 'view_publish': f['view_publish'], 'view': f['view'],
            'model': {'name': model['name'], 'type': model['type'], 'intercept': model['intercept'],
                      'factors': factors_out, 'val_mae': model['val_mae'], 'val_rmse': model['val_rmse'],
                      'val_dir_acc': model['val_dir_acc'], 'all_scores': model['all_scores'],
                      'compare15': model['compare15']},
        })
        print(f"  -> {model['type']} {model['name']} MAE={model['val_mae']}")

    conn.close()
    js = 'window.FUND_DATA = ' + json.dumps(web, ensure_ascii=False) + ';'
    open(OUT, 'w', encoding='utf-8').write(js)
    print(f'\ndata.js 已生成，基金数 {len(web["funds"])}')


if __name__ == '__main__':
    main()
