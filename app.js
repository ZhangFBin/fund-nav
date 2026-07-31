/* 交银基金重点产品净值表现 - SPA */
(function () {
  var D = window.FUND_DATA;
  var app = document.getElementById('app');
  document.getElementById('upd').textContent = '净值更新至 ' + D.funds[0].nav_date;

  function fmtPct(v, digits) {
    if (v === null || v === undefined || isNaN(v)) return '<span class="flat">--</span>';
    var cls = v > 0 ? 'up' : (v < 0 ? 'down' : 'flat');
    var sign = v > 0 ? '+' : '';
    return '<span class="' + cls + '">' + sign + Number(v).toFixed(digits === undefined ? 2 : digits) + '%</span>';
  }
  function esc(s) { return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
  function typeTag(t) {
    if (!t) return '';
    var gold = /FOF|债券/.test(t) ? ' gold' : '';
    return '<span class="tag' + gold + '">' + esc(t) + '</span>';
  }

  /* ---------- 首页 ---------- */
  function renderHome() {
    var html = '<div class="card" style="padding:14px 16px">' +
      '<button class="est-btn" id="estAllBtn" onclick="window.__runEstAll()">一键测算全部产品估值</button>' +
      '<div class="est-note" id="estAllNote" style="display:none"></div></div>';
    D.funds.forEach(function (f) {
      html += '<a class="card fund-card" href="#/' + f.code + '">' +
        '<div class="fc-head"><div><span class="fc-name">' + esc(f.name) + '</span><span class="fc-code">' + f.code + '</span></div>' +
        '<div>' + typeTag(f.type) + '</div></div>' +
        '<div class="fc-nav"><div class="nav-v">' + f.nav.toFixed(4) + '</div>' +
        '<div class="nav-d">' + f.nav_date + ' · 日涨跌 ' + fmtPct(f.day_growth) + '</div></div>' +
        '<div class="fc-rets">' +
        '<div class="ret-item"><div class="rv">' + fmtPct(f.ret_1w) + '</div><div class="rl">近1周</div></div>' +
        '<div class="ret-item"><div class="rv">' + fmtPct(f.ret_1m) + '</div><div class="rl">近1月</div></div>' +
        '<div class="ret-item"><div class="rv">' + fmtPct(f.ret_3m) + '</div><div class="rl">近3月</div></div>' +
        '<div class="ret-item"><div class="rv">' + fmtPct(f.ret_ytd) + '</div><div class="rl">今年来</div></div>' +
        '</div>' +
        '<div class="fc-foot"><span>基金经理：' + esc(f.manager) + '</span>' +
        '<span class="mae-badge" id="est-badge-' + f.code + '">估值手动测算 ›</span></div>' +
        '</a>';
    });
    app.innerHTML = html;
    window.scrollTo(0, 0);
  }

  /* ---------- SVG 净值走势图 ---------- */
  function drawNavChart(series) {
    var W = 800, H = 240, P = { l: 46, r: 14, t: 18, b: 26 };
    var vals = series.map(function (s) { return s.v; });
    var min = Math.min.apply(null, vals), max = Math.max.apply(null, vals);
    var pad = (max - min) * 0.08 || 0.001; min -= pad; max += pad;
    var iw = W - P.l - P.r, ih = H - P.t - P.b;
    function X(i) { return P.l + iw * i / (series.length - 1); }
    function Y(v) { return P.t + ih * (1 - (v - min) / (max - min)); }
    var path = '', area = '';
    series.forEach(function (s, i) {
      path += (i === 0 ? 'M' : 'L') + X(i).toFixed(1) + ',' + Y(s.v).toFixed(1);
    });
    area = path + 'L' + X(series.length - 1).toFixed(1) + ',' + (P.t + ih) + 'L' + P.l + ',' + (P.t + ih) + 'Z';
    var last = series[series.length - 1];
    var first = series[0];
    var up = last.v >= first.v;
    var lineColor = up ? '#e0453a' : '#1a9e54';
    var mid = series[Math.floor(series.length / 2)];
    return '<svg viewBox="0 0 ' + W + ' ' + H + '" style="width:100%;display:block" xmlns="http://www.w3.org/2000/svg">' +
      '<defs><linearGradient id="g1" x1="0" y1="0" x2="0" y2="1">' +
      '<stop offset="0" stop-color="' + lineColor + '" stop-opacity=".18"/>' +
      '<stop offset="1" stop-color="' + lineColor + '" stop-opacity="0"/></linearGradient></defs>' +
      '<path d="' + area + '" fill="url(#g1)"/>' +
      '<path d="' + path + '" fill="none" stroke="' + lineColor + '" stroke-width="2.2"/>' +
      '<text x="' + (P.l - 6) + '" y="' + (Y(max) + 10) + '" text-anchor="end" font-size="12" fill="#8a8f99">' + max.toFixed(4) + '</text>' +
      '<text x="' + (P.l - 6) + '" y="' + (Y(min) + 4) + '" text-anchor="end" font-size="12" fill="#8a8f99">' + min.toFixed(4) + '</text>' +
      '<line x1="' + P.l + '" y1="' + Y(max) + '" x2="' + (W - P.r) + '" y2="' + Y(max) + '" stroke="#eceff5" stroke-dasharray="3,3"/>' +
      '<line x1="' + P.l + '" y1="' + Y(min) + '" x2="' + (W - P.r) + '" y2="' + Y(min) + '" stroke="#eceff5" stroke-dasharray="3,3"/>' +
      '<text x="' + P.l + '" y="' + (H - 8) + '" font-size="12" fill="#8a8f99">' + first.d.slice(5) + '</text>' +
      '<text x="' + ((W) / 2) + '" y="' + (H - 8) + '" text-anchor="middle" font-size="12" fill="#8a8f99">' + mid.d.slice(5) + '</text>' +
      '<text x="' + (W - P.r) + '" y="' + (H - 8) + '" text-anchor="end" font-size="12" fill="#8a8f99">' + last.d.slice(5) + '</text>' +
      '<circle cx="' + X(series.length - 1) + '" cy="' + Y(last.v) + '" r="4" fill="' + lineColor + '"/>' +
      '<circle cx="' + X(series.length - 1) + '" cy="' + Y(last.v) + '" r="7" fill="' + lineColor + '" opacity=".25"/>' +
      '</svg>';
  }

  /* ---------- 详情页 ---------- */
  function renderDetail(code) {
    var f = null;
    D.funds.forEach(function (x) { if (x.code === code) f = x; });
    if (!f) { renderHome(); return; }
    var m = f.model;

    var html = '<a class="back" href="#/">‹ 返回产品列表</a>';

    // 头部卡
    html += '<div class="card">' +
      '<div class="d-title">' + esc(f.name) + ' <span style="font-size:13px;color:var(--sub);font-weight:400">' + f.code + '</span></div>' +
      '<div class="d-sub">' + esc(f.full_name) + '</div>' +
      '<div class="d-tags">' + typeTag(f.type) +
      (f.risk ? '<span class="tag gold">' + esc(f.risk) + '</span>' : '') + '</div>' +
      '<div class="nav-main"><div class="big">' + f.nav.toFixed(4) + '</div>' +
      '<div class="chg">' + fmtPct(f.day_growth) + '</div>' +
      '<div class="dt">' + f.nav_date + '</div></div>' +
      '<div class="info-grid">' +
      '<div class="info-cell"><div class="il">基金经理</div><div class="iv">' + esc(f.manager) + '</div></div>' +
      '<div class="info-cell"><div class="il">基金规模</div><div class="iv">' + (f.scale_yi ? f.scale_yi + '亿' : '--') + '</div></div>' +
      '<div class="info-cell"><div class="il">业绩基准</div><div class="iv" style="font-size:12px">' + esc(f.benchmark || '--') + '</div></div>' +
      '</div>' +
      '<div class="fc-rets" style="margin-top:12px">' +
      '<div class="ret-item"><div class="rv">' + fmtPct(f.ret_1w) + '</div><div class="rl">近1周</div></div>' +
      '<div class="ret-item"><div class="rv">' + fmtPct(f.ret_1m) + '</div><div class="rl">近1月</div></div>' +
      '<div class="ret-item"><div class="rv">' + fmtPct(f.ret_3m) + '</div><div class="rl">近3月</div></div>' +
      '<div class="ret-item"><div class="rv">' + fmtPct(f.ret_ytd) + '</div><div class="rl">今年来</div></div>' +
      '</div>' +
      (f.note ? '<div class="hint">' + esc(f.note) + '</div>' : '') +
      '<div class="link-row">' +
      '<a class="ext-link primary" href="' + f.tt_link + '" target="_blank" rel="noopener">天天基金 · 详情资料</a>' +
      '<a class="ext-link ghost" href="' + f.tt_f10 + '" target="_blank" rel="noopener">持仓明细(F10)</a>' +
      '</div></div>';

    // 净值走势
    html += '<div class="card"><div class="section-t">净值走势（近60个交易日）</div>' +
      '<div class="chart-box">' + drawNavChart(f.nav_series) + '</div></div>';

    // 15日验证对比
    html += '<div class="card"><div class="section-t">模型验证：近15个交易日 真实 vs 估算</div>' +
      '<table class="cmp-table"><tr><th>日期</th><th>真实涨跌</th><th>模型估算</th><th>偏差</th></tr>';
    m.compare15.slice().reverse().forEach(function (r) {
      var dcls = Math.abs(r.diff) <= m.val_mae ? 'flat' : (r.diff > 0 ? 'up' : 'down');
      html += '<tr><td>' + r.date.slice(5) + '</td><td>' + fmtPct(r.actual) + '</td><td>' + fmtPct(r.est) + '</td>' +
        '<td class="' + dcls + '">' + (r.diff > 0 ? '+' : '') + r.diff.toFixed(3) + '</td></tr>';
    });
    html += '</table></div>';

    // 重仓
    if (f.holdings.length) {
      html += '<div class="card"><div class="section-t">前十大重仓股（' + esc(f.holding_period) + ' 季报披露）</div>';
      var maxW = f.holdings[0] ? f.holdings[0].weight : 1;
      f.holdings.forEach(function (h, i) {
        html += '<div class="hold-row"><div class="hold-rank' + (i < 3 ? ' top3' : '') + '">' + (i + 1) + '</div>' +
          '<div class="hold-name"><div class="hn">' + esc(h.name) + '</div><div class="hc">' + h.code + ' · ' + esc(h.industry || '') + '</div></div>' +
          '<div class="hold-bar-box"><div class="hold-bar" style="width:' + Math.max(4, h.weight / maxW * 100).toFixed(1) + '%"></div></div>' +
          '<div class="hold-w">' + h.weight.toFixed(2) + '%</div></div>';
      });
      html += '</div>';
    }
    if (f.fund_holdings.length) {
      html += '<div class="card"><div class="section-t">前十大重仓基金（' + esc(f.holding_period) + ' 季报披露）</div>';
      var maxW2 = f.fund_holdings[0] ? f.fund_holdings[0].weight : 1;
      f.fund_holdings.forEach(function (h, i) {
        html += '<div class="hold-row"><div class="hold-rank' + (i < 3 ? ' top3' : '') + '">' + (i + 1) + '</div>' +
          '<div class="hold-name"><div class="hn" style="font-size:13px">' + esc(h.name) + '</div><div class="hc">' + h.code + '</div></div>' +
          '<div class="hold-bar-box"><div class="hold-bar" style="width:' + Math.max(4, h.weight / maxW2 * 100).toFixed(1) + '%"></div></div>' +
          '<div class="hold-w">' + h.weight.toFixed(2) + '%</div></div>';
      });
      if (f.bond_holdings && f.bond_holdings.length) {
        html += '<div style="margin-top:10px;font-size:12px;color:var(--sub)">直投债券：';
        f.bond_holdings.forEach(function (b) { html += esc(b.name) + ' ' + b.weight.toFixed(2) + '%；'; });
        html += '</div>';
      }
      html += '</div>';
    }

    // 季报观点
    html += '<div class="card"><div class="section-t">基金经理最新季报观点</div>' +
      '<div class="view-src">' + esc(f.view_title) + (f.view_publish ? ' · 披露于 ' + f.view_publish : '') + ' · 摘自"报告期内基金的投资策略和运作分析"</div>' +
      '<div class="view-body">' + esc(f.view || '暂无') + '</div></div>';

    app.innerHTML = html;
    window.scrollTo(0, 0);
  }

  /* ---------- 实时行情（腾讯，script标签跨域） ---------- */
  function loadTxQuotes(txCodes, cb) {
    if (!txCodes.length) { cb({}); return; }
    var s = document.createElement('script');
    var done = false;
    s.src = 'https://qt.gtimg.cn/q=' + txCodes.join(',');
    s.onload = function () {
      if (done) return; done = true;
      var out = {};
      txCodes.forEach(function (c) {
        var v = window['v_' + c];
        if (typeof v === 'string') {
          var arr = v.split('~');
          var cur = parseFloat(arr[3]), prev = parseFloat(arr[4]);
          if (cur > 0 && prev > 0) out[c] = { cur: cur, prev: prev, ret: (cur / prev - 1) * 100, name: arr[1] };
        }
      });
      document.head.removeChild(s);
      cb(out);
    };
    s.onerror = function () { if (!done) { done = true; cb({}); } };
    document.head.appendChild(s);
    setTimeout(function () { if (!done) { done = true; try { document.head.removeChild(s); } catch (e) {} cb({}); } }, 8000);
  }

  /* ---------- 统一估值 ---------- */
  window.__runEstAll = function () {
    var btn = document.getElementById('estAllBtn');
    var note = document.getElementById('estAllNote');
    btn.disabled = true; btn.textContent = '正在获取实时行情…';
    var txSet = {};
    D.funds.forEach(function (f) {
      f.model.factors.forEach(function (fa) { if (fa.tx) txSet[fa.tx] = 1; });
    });
    loadTxQuotes(Object.keys(txSet), function (quotes) {
      var now = new Date();
      var hh = now.getHours() + now.getMinutes() / 60;
      var session = (hh >= 9.5 && hh < 15) ? '交易时段，因子为盘中实时价' : '非交易时段，因子为最近收盘价';
      D.funds.forEach(function (f) {
        var m = f.model, est = m.intercept;
        m.factors.forEach(function (fa) {
          var r = null;
          if (fa.tx && quotes[fa.tx]) r = quotes[fa.tx].ret;
          else if (fa.static) r = fa.static.ret;
          if (r !== null) est += fa.beta * r;
        });
        var estNav = f.nav * (1 + est / 100);
        var badge = document.getElementById('est-badge-' + f.code);
        if (badge) {
          var cls = est > 0 ? 'up' : (est < 0 ? 'down' : 'flat');
          badge.innerHTML = '估值 <b class="' + cls + '" style="font-size:13px">' + estNav.toFixed(4) +
            ' (' + (est > 0 ? '+' : '') + est.toFixed(2) + '%)</b>';
          badge.style.background = '#fff';
          badge.style.border = '1px solid var(--line)';
        }
      });
      note.style.display = 'block';
      note.innerHTML = '测算时间 ' + now.toLocaleString('zh-CN') + ' · ' + session +
        '；FOF 部分因子采用最近一期子基金收益。<br>估值为模型测算结果，仅供参考，实际净值以基金公司官方披露为准。';
      btn.disabled = false; btn.textContent = '重新测算全部产品估值';
    });
  };

  /* ---------- 访问量统计（CounterAPI，免费免注册） ---------- */
  (function trackVisit() {
    var BASE = 'https://api.counterapi.dev/v1/jysld-fund-nav/total';
    var elT = document.getElementById('visit-total');
    var elD = document.getElementById('visit-today');
    function showTotal(n) { if (elT) elT.textContent = '累计访问 ' + n + ' 次'; }
    function showToday(n) { if (elD && n > 0) elD.textContent = '· 今日 ' + n + ' 次'; }
    function fetchList() {
      fetch(BASE + '/list?group_by=day&order_by=desc')
        .then(function (r) { return r.json(); })
        .then(function (arr) { if (arr && arr[0]) showToday(arr[0].count || 0); })
        .catch(function () {});
    }
    if (sessionStorage.getItem('jysld_visited')) {
      // 同一会话不重复计数，仅展示
      fetch(BASE + '/').then(function (r) { return r.json(); }).then(function (d) { showTotal(d.count); }).catch(function () { showTotal('--'); });
      fetchList();
      return;
    }
    sessionStorage.setItem('jysld_visited', '1');
    // 首次访问：+1
    fetch(BASE + '/up')
      .then(function (r) { return r.json(); })
      .then(function (d) { showTotal(d.count); fetchList(); })
      .catch(function () { showTotal('--'); fetchList(); });
  })();

  /* ---------- 路由 ---------- */
  function route() {
    var h = location.hash.replace(/^#\/?/, '');
    if (h && /^[0-9]{6}$/.test(h)) renderDetail(h);
    else renderHome();
  }
  window.addEventListener('hashchange', route);
  route();
})();
