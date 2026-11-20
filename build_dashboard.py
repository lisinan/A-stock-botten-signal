#!/home/lisinan/miniforge3/envs/qmt/bin/python
# -*- coding: utf-8 -*-
"""
A股见底信号仪表盘 —— 拉取 tushare 真实数据，生成自包含 HTML 看板。
用法: /home/lisinan/miniforge3/envs/qmt/bin/python build_dashboard.py
"""
import tushare as ts
import pandas as pd
import numpy as np
import json, datetime, os

END = datetime.date.today().strftime("%Y%m%d")
START = "20180102"
IDX = "000300.SH"
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_HTML = os.path.join(OUT_DIR, "index.html")

pro = ts.pro_api()

def pct_rank(series, value):
    s = pd.Series(series).dropna()
    return float((s < value).mean() * 100)

# ---------- 指数估值 + 行情 ----------
ib = pro.index_dailybasic(ts_code=IDX, start_date=START, end_date=END).sort_values("trade_date").reset_index(drop=True)
px = pro.index_daily(ts_code=IDX, start_date=START, end_date=END).sort_values("trade_date").reset_index(drop=True)

ib = ib[["trade_date", "pe_ttm", "pb", "turnover_rate"]].dropna(subset=["pe_ttm"])
px = px[["trade_date", "close", "amount"]]
px["ma250"] = px["close"].rolling(250).mean()
px["amt20"] = px["amount"].rolling(20).mean()

last_date = px["trade_date"].iloc[-1]
close = px["close"].iloc[-1]
ma250 = px["ma250"].iloc[-1]

# 估值分位
last_ib = ib.iloc[-1]
pe = last_ib["pe_ttm"]; pb = last_ib["pb"]
pe_pct = pct_rank(ib["pe_ttm"], pe)
pb_pct = pct_rank(ib["pb"], pb)

# 价格
w5 = px[px["trade_date"] >= "20211201"]
hi5 = w5["close"].max(); hi5_date = w5.loc[w5["close"].idxmax(), "trade_date"]
dd = (close / hi5 - 1) * 100
vs_ma250 = (close / ma250 - 1) * 100
c1y_date = (pd.Timestamp(last_date) - pd.Timedelta(days=365)).strftime("%Y%m%d")
c1y = px[px["trade_date"] <= c1y_date]["close"].iloc[-1]
chg1y = (close / c1y - 1) * 100

# 成交额分位
amt20 = px["amt20"].iloc[-1] / 1e5  # 亿元
amt_pct = pct_rank(px["amt20"].dropna(), px["amt20"].iloc[-1])

# ---------- 破净率时间序列 ----------
cal = sorted(pro.trade_cal(exchange="SSE", start_date="20200101", end_date=END, is_open="1")["cal_date"].tolist())
sample = cal[::20]
if sample[-1] != cal[-1]:
    sample.append(cal[-1])
rows = []
for d in sample:
    try:
        db = pro.daily_basic(trade_date=d, fields="ts_code,pb").dropna(subset=["pb"])
        if len(db) < 1000:
            continue
        rows.append((d, round((db["pb"] < 1).mean() * 100, 2)))
    except Exception:
        pass
bts = pd.DataFrame(rows, columns=["date", "broken_pct"])
cur_broken = float(bts["broken_pct"].iloc[-1])
broken_rank = pct_rank(bts["broken_pct"], cur_broken)

# ---------- 两融 ----------
m = pro.margin(start_date="20240101", end_date=END)
m = m.groupby("trade_date")["rzye"].sum().reset_index().sort_values("trade_date")
rz_now = m["rzye"].iloc[-1] / 1e8
rz_hi = m["rzye"].max()
rz_off = (m["rzye"].iloc[-1] / rz_hi - 1) * 100

# ---------- 流动性 / 资金面（补充） ----------
# Shibor 短期资金价格（回笼→资金紧→短端利率上行）
sh = pro.shibor(start_date="20230101", end_date=END).sort_values("date")
# M1-M2 剪刀差（资金活化，回升=流动性改善）
mm = pro.cn_m(start_m="202301", end_m=END[:6]).sort_values("month")
mm["gap"] = (mm["m1_yoy"] - mm["m2_yoy"]).round(1)
# 社会融资增量（月度，亿元）
try:
    sf = pro.sf_month(start_m="202301", end_m=END[:6]).sort_values("month")
except Exception:
    sf = pd.DataFrame(columns=["month", "inc_month"])

# ---------- 打分卡 ----------
cards = [
    {"dim": "估值", "name": "PE_TTM", "value": f"{pe:.2f}", "note": f"8年分位 {pe_pct:.0f}%", "pass": bool(pe_pct < 20)},
    {"dim": "估值", "name": "PB", "value": f"{pb:.2f}", "note": f"8年分位 {pb_pct:.0f}%", "pass": bool(pb_pct < 20)},
    {"dim": "价格", "name": "距5年高点回撤", "value": f"{dd:.1f}%", "note": f"高点 {hi5_date}", "pass": bool(dd <= -30)},
    {"dim": "价格", "name": "相对年线MA250", "value": f"{vs_ma250:+.1f}%", "note": f"MA250={ma250:.0f}", "pass": bool(vs_ma250 < 0)},
    {"dim": "价格", "name": "近1年涨跌", "value": f"{chg1y:+.1f}%", "note": "参考", "pass": bool(chg1y < 0)},
    {"dim": "量能", "name": "成交额20日均", "value": f"{amt20:.0f}亿", "note": f"8年分位 {amt_pct:.0f}%", "pass": bool(amt_pct < 20)},
    {"dim": "宽度", "name": "破净股占比", "value": f"{cur_broken:.1f}%", "note": f"5年分位 {broken_rank:.0f}%", "pass": bool(cur_broken > 8)},
    {"dim": "杠杆", "name": "两融较高点", "value": f"{rz_off:+.0f}%", "note": f"{rz_now:.0f}亿元", "pass": bool(rz_off <= -15)},
]
hits = sum(1 for c in cards if c["pass"])
total = len(cards)

# ---------- 生成最终结论（数据驱动） ----------
ratio = hits / total
if ratio >= 0.75:
    verdict_level, verdict_title = "high", "底部特征较强 · 可积极分批布局"
elif ratio >= 0.4:
    verdict_level, verdict_title = "mid", "底部区域已现 · 待右侧确认"
else:
    verdict_level, verdict_title = "low", "未见底 · 趋势仍偏弱"

earnings_kill = (pe_pct > 50 and pb_pct < 30)
points = []
points.append(f"8 项底部信号命中 <b>{hits}/{total}</b>，处于「{'偏充分' if ratio>=0.75 else ('部分到位' if ratio>=0.4 else '不足')}」状态。")
points.append(f"<b>估值：</b>PE_TTM {pe:.2f}（8年分位 <b>{pe_pct:.0f}%</b>，{'不便宜' if pe_pct>50 else '偏低'}），PB {pb:.2f}（分位 {pb_pct:.0f}%，{'低' if pb_pct<30 else '中高'}）。" + ("<b>PE高而PB低 = 典型『业绩杀』</b>：E(盈利)下滑推高PE，股价已跌到净资产附近，说明<b>业绩底尚未出现</b>。" if earnings_kill else ""))
points.append(f"<b>价格：</b>距近5年高点 <b>{dd:.1f}%</b>，{'仍在' if vs_ma250<0 else '已站上'}年线（相对MA250 {vs_ma250:+.1f}%）→ <b>{'下跌趋势尚未破坏' if vs_ma250<0 else '趋势有转强迹象'}</b>。")
points.append(f"<b>市场宽度：</b>破净股占比 <b>{cur_broken:.1f}%</b>（5年分位 {broken_rank:.0f}%）+ 近期持续攀升 → 整体已大面积跌破净资产，是<b>强底部信号</b>，但尚未见到『见顶回落』的右侧拐点。")
points.append(f"<b>量能：</b>成交额处于近8年 <b>{amt_pct:.0f}%</b> 分位 → <b>{'地量，卖压已充分出清' if amt_pct<20 else '并非地量，更像放量下跌/高换手，多空分歧大、卖压未缩量出清'}</b>。")
points.append(f"<b>杠杆：</b>融资余额较高点 <b>{rz_off:+.0f}%</b>（现 {rz_now:.0f} 亿）→ 杠杆资金{'已大幅出清' if rz_off<=-15 else '出清尚不充分'}。")

actions = []
actions.append("<b>左侧（已可开始）：</b>破净率高 + 杠杆出清，估值区已进入可<b>分批、分档</b>布局阶段，但切忌一次性满仓，务必留足弹药。")
actions.append("<b>右侧确认（加仓信号，任一明确出现再加）：</b>① 破净率/创新低占比<b>见顶回落</b>；② 指数<b>放量站上年线(MA250)</b>；③ 成交额先缩至地量、再重新放大。")
actions.append("<b>盯业绩底：</b>PE高+PB低意味着在杀盈利，需等 PMI、工业企业利润、社融等盈利端指标企稳，才具备『戴维斯双升』前提。")

conclusion = {"level": verdict_level, "title": verdict_title, "points": points, "actions": actions}

data = {
    "last_date": last_date,
    "close": round(float(close), 2),
    "pe": round(float(pe), 2), "pe_pct": round(pe_pct, 1),
    "pb": round(float(pb), 3), "pb_pct": round(pb_pct, 1),
    "dd": round(dd, 1), "vs_ma250": round(vs_ma250, 1),
    "cards": cards, "hits": hits, "total": total, "conclusion": conclusion,
    "price": {"dates": px["trade_date"].tolist(), "close": px["close"].round(2).tolist(), "ma250": [None if pd.isna(x) else round(x,2) for x in px["ma250"]]},
    "val": {"dates": ib["trade_date"].tolist(), "pe": ib["pe_ttm"].round(2).tolist(), "pb": ib["pb"].round(3).tolist()},
    "broken": {"dates": bts["date"].tolist(), "vals": bts["broken_pct"].tolist()},
    "amt": {"dates": px["trade_date"].tolist(), "vals": [None if pd.isna(x) else round(x/1e5,1) for x in px["amt20"]]},
    "margin": {"dates": m["trade_date"].tolist(), "vals": [round(x/1e8,0) for x in m["rzye"]]},
    "shibor": {"dates": sh["date"].tolist(), "on": sh["on"].round(3).tolist(), "w1": sh["1w"].round(3).tolist()},
    "m1m2": {"months": mm["month"].tolist(), "m1": mm["m1_yoy"].tolist(), "m2": mm["m2_yoy"].tolist(), "gap": mm["gap"].tolist()},
    "sf": {"months": sf["month"].tolist(), "inc": [round(x,0) for x in sf["inc_month"]]},
    "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
}

# ---------- 生成 HTML ----------
HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>A股见底信号仪表盘</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
  :root{--bg:#0f1117;--panel:#171a23;--line:#242938;--txt:#e6e9f0;--sub:#8b93a7;
        --good:#22d3a7;--bad:#f0564b;--warn:#f5a623;--accent:#4f8cff;}
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:var(--txt);font-family:system-ui,-apple-system,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;padding:22px;line-height:1.5}
  .wrap{max-width:1440px;margin:0 auto}
  header{display:flex;flex-wrap:wrap;align-items:center;gap:18px;justify-content:space-between;margin-bottom:18px}
  h1{font-size:22px;font-weight:700}
  h1 span{color:var(--accent)}
  .meta{color:var(--sub);font-size:13px}
  .verdict{display:flex;align-items:center;gap:16px;background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:14px 22px}
  .score{font-size:40px;font-weight:800;letter-spacing:-1px}
  .score small{font-size:18px;color:var(--sub);font-weight:600}
  .badge{padding:4px 12px;border-radius:20px;font-size:13px;font-weight:700}
  .badge.mid{background:rgba(245,166,35,.15);color:var(--warn);border:1px solid rgba(245,166,35,.35)}
  .badge.low{background:rgba(240,86,75,.15);color:var(--bad);border:1px solid rgba(240,86,75,.35)}
  .badge.high{background:rgba(34,211,167,.15);color:var(--good);border:1px solid rgba(34,211,167,.35)}
  .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:22px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px 16px;position:relative;overflow:hidden;transition:.2s}
  .card:hover{transform:translateY(-2px);border-color:#333}
  .card::before{content:"";position:absolute;left:0;top:0;bottom:0;width:4px}
  .card.on::before{background:var(--good)}
  .card.off::before{background:#3a4152}
  .card .dim{font-size:11px;color:var(--sub);letter-spacing:1px}
  .card .nm{font-size:13px;color:#c3c9d6;margin:4px 0 8px}
  .card .val{font-size:24px;font-weight:700}
  .card .note{font-size:12px;color:var(--sub);margin-top:4px}
  .card .dot{position:absolute;right:14px;top:14px;font-size:16px}
  .card.on .dot{color:var(--good)}
  .card.off .dot{color:#3a4152}
  h2{font-size:15px;font-weight:600;color:#c3c9d6;margin:26px 0 12px;display:flex;align-items:center;gap:8px}
  h2::before{content:"";width:4px;height:15px;background:var(--accent);border-radius:2px}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
  .chart{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:10px}
  .chart.full{grid-column:1 / -1}
  .chart .c{width:100%;height:320px}
  .chart.full .c{height:360px}
  .foot{color:var(--sub);font-size:12px;margin-top:22px;padding-top:14px;border-top:1px solid var(--line)}
  .legend-note{color:var(--sub);font-size:12px;margin:-4px 0 10px}
  .explain{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px 18px;margin-bottom:8px}
  .explain summary{cursor:pointer;font-weight:700;font-size:15px;color:#c3c9d6;list-style:none}
  .explain summary::-webkit-details-marker{display:none}
  .explain-body{margin-top:12px;font-size:13.5px;color:#c3c9d6}
  .explain-body p{margin:6px 0}
  .two-col{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:12px 0}
  .col-box{background:#12141c;border:1px solid var(--line);border-radius:10px;padding:12px 14px}
  .col-h{font-weight:700;font-size:13px;margin-bottom:8px;padding-left:10px;position:relative}
  .col-h::before{content:"";position:absolute;left:0;top:2px;bottom:2px;width:3px;border-radius:2px}
  .col-h.left::before{background:var(--accent)}
  .col-h.right::before{background:var(--good)}
  .col-box ul{margin:0;padding-left:18px}
  .col-box li{margin:5px 0}
  .tip{background:rgba(79,140,255,.08);border-left:3px solid var(--accent);padding:8px 12px;border-radius:8px;color:#b9c1d1}
  .concl{background:linear-gradient(135deg,rgba(245,166,35,.08),rgba(240,86,75,.05));border:1px solid rgba(245,166,35,.3);border-radius:16px;padding:20px 22px;margin-top:8px}
  .concl-head{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-bottom:16px}
  .concl-title{font-size:22px;font-weight:800}
  .concl-sub{font-size:13px;font-weight:700;color:var(--warn);margin:4px 0 8px;letter-spacing:.5px}
  .concl-points{margin:0 0 18px;padding-left:20px;font-size:14px;color:#d3d8e3;line-height:1.7}
  .concl-points li{margin:7px 0}
  .concl-points b{color:#fff}
  @media(max-width:820px){.grid{grid-template-columns:1fr}.two-col{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div>
      <h1>A股见底信号 <span>仪表盘</span></h1>
      <div class="meta">基准 沪深300 (000300.SH) · 数据截至 __LAST_DATE__ · 生成于 __GEN__</div>
    </div>
    <div class="verdict">
      <div>
        <div class="meta">底部信号命中</div>
        <div class="score"><span id="hit">0</span><small>/__TOTAL__</small></div>
      </div>
      <div id="verdictBadge" class="badge mid">...</div>
    </div>
  </header>

  <div class="cards" id="cards"></div>

  <details class="explain" open>
    <summary>🧭 如何解读本看板</summary>
    <div class="explain-body">
      <p><b>核心逻辑：底部不是猜的，是一组信号从「同时很差」转向「同时转好」的过程。</b>信号分两类：</p>
      <div class="two-col">
        <div class="col-box">
          <div class="col-h left">左侧信号（先到）</div>
          <ul>
            <li><b>估值分位</b>：PE/PB 处于历史低位（&lt;20%）→ 便宜</li>
            <li><b>破净率</b>：跌破净资产的股票占比（&gt;8~10%）→ 整体低估</li>
            <li><b>两融</b>：融资余额较高点回落（&lt;-15%）→ 杠杆出清</li>
          </ul>
        </div>
        <div class="col-box">
          <div class="col-h right">右侧信号（后到，用于确认）</div>
          <ul>
            <li><b>价格</b>：放量站上年线(MA250)，下跌趋势被打破</li>
            <li><b>量能</b>：先缩至地量、再重新放大</li>
            <li><b>宽度拐点</b>：破净率/新低占比见顶回落</li>
          </ul>
        </div>
      </div>
      <p class="tip">📊 卡片<b>亮绿色</b>=该信号已呈现底部特征，<b>灰色</b>=未确认。<b>命中越多越接近底</b>，但只有<b>右侧信号出现才算真正确认见底</b>。阈值（分位&lt;20%、破净&gt;8%、回撤&lt;-30% 等）为经验参考值，非普适规律。</p>
    </div>
  </details>

  <h2>沪深300 收盘价 与 年线(MA250)</h2>
  <div class="grid">
    <div class="chart full"><div class="c" id="priceChart"></div></div>
  </div>

  <h2>估值走势 (PE_TTM / PB)</h2>
  <div class="legend-note">PE 分位 __PE_PCT__% · PB 分位 __PB_PCT__% —— PE 高而 PB 低 = 「业绩杀」特征，业绩底未现</div>
  <div class="grid">
    <div class="chart full"><div class="c" id="valChart"></div></div>
  </div>

  <h2>市场宽度 · 破净率 与 量能/杠杆</h2>
  <div class="grid">
    <div class="chart"><div class="c" id="brokenChart"></div></div>
    <div class="chart"><div class="c" id="amtChart"></div></div>
    <div class="chart full"><div class="c" id="marginChart"></div></div>
  </div>

  <h2>💧 流动性 / 资金面（补充）</h2>
  <div class="legend-note">Tushare 无央行公开市场操作(逆回购/MLF 净投放·回笼)原始接口，以下为反映资金面松紧的间接指标：短端利率↑=收紧(回笼)，M1-M2 剪刀差↑=资金活化改善。</div>
  <div class="grid">
    <div class="chart full"><div class="c" id="shiborChart"></div></div>
    <div class="chart"><div class="c" id="m1m2Chart"></div></div>
    <div class="chart"><div class="c" id="sfChart"></div></div>
  </div>

  <h2>📌 最终结论</h2>
  <div class="concl" id="concl">
    <div class="concl-head">
      <span id="conclBadge" class="badge mid">…</span>
      <span id="conclTitle" class="concl-title"></span>
    </div>
    <div class="concl-sub">判断依据</div>
    <ul id="conclPoints" class="concl-points"></ul>
    <div class="concl-sub">行动方案（框架，非荐股）</div>
    <ul id="conclActions" class="concl-points"></ul>
  </div>

  <div class="foot">
    ⚠️ 本看板为基于公开数据的量化信号展示，<b>不构成投资建议</b>。数据来源：Tushare Pro。信号阈值（如破净率&gt;8%、回撤&gt;-30%、分位&lt;20%）为经验参考值，非普适规律。
  </div>
</div>

<script>
const D = __DATA__;
const C = {good:'#22d3a7',bad:'#f0564b',warn:'#f5a623',accent:'#4f8cff',sub:'#8b93a7',line:'#242938',grid:'#1d2230',txt:'#e6e9f0'};
const axisCommon = {axisLine:{lineStyle:{color:C.line}},axisLabel:{color:C.sub},splitLine:{lineStyle:{color:C.grid}}};

// 卡片
const cardsEl = document.getElementById('cards');
D.cards.forEach(c=>{
  const el=document.createElement('div');
  el.className='card '+(c.pass?'on':'off');
  el.innerHTML=`<div class="dot">${c.pass?'●':'○'}</div>
    <div class="dim">${c.dim}</div><div class="nm">${c.name}</div>
    <div class="val" style="color:${c.pass?'var(--good)':'var(--txt)'}">${c.value}</div>
    <div class="note">${c.note}</div>`;
  cardsEl.appendChild(el);
});
document.getElementById('hit').textContent = D.hits;
const vb=document.getElementById('verdictBadge');
const ratio=D.hits/D.total;
if(ratio>=0.75){vb.className='badge high';vb.textContent='底部特征较强';}
else if(ratio>=0.4){vb.className='badge mid';vb.textContent='底部区域 · 待右侧确认';}
else{vb.className='badge low';vb.textContent='未见底 · 趋势偏弱';}

// 最终结论
if(D.conclusion){
  const cc=D.conclusion;
  const cb=document.getElementById('conclBadge');
  cb.className='badge '+(cc.level==='high'?'high':cc.level==='mid'?'mid':'low');
  cb.textContent=cc.level==='high'?'强信号':cc.level==='mid'?'中性偏底':'偏弱';
  document.getElementById('conclTitle').textContent=cc.title;
  const ulP=document.getElementById('conclPoints');
  cc.points.forEach(t=>{const li=document.createElement('li');li.innerHTML=t;ulP.appendChild(li);});
  const ulA=document.getElementById('conclActions');
  cc.actions.forEach(t=>{const li=document.createElement('li');li.innerHTML=t;ulA.appendChild(li);});
}

function mk(id,opt){const ch=echarts.init(document.getElementById(id));ch.setOption(opt);return ch;}
const charts=[];
window.addEventListener('resize',()=>charts.forEach(c=>c.resize()));

// 价格
charts.push(mk('priceChart',{
  backgroundColor:'transparent',tooltip:{trigger:'axis'},legend:{data:['收盘价','MA250'],textStyle:{color:C.sub},top:0},
  grid:{left:56,right:24,top:34,bottom:40},
  xAxis:{type:'category',data:D.price.dates,boundaryGap:false,...axisCommon,axisLabel:{color:C.sub,formatter:v=>v.slice(0,4)+'-'+v.slice(4,6)}},
  yAxis:{type:'value',scale:true,...axisCommon},
  series:[
    {name:'收盘价',type:'line',data:D.price.close,showSymbol:false,lineStyle:{color:C.accent,width:1.6},itemStyle:{color:C.accent}},
    {name:'MA250',type:'line',data:D.price.ma250,showSymbol:false,lineStyle:{color:C.warn,width:1.2,type:'dashed'},itemStyle:{color:C.warn}}
  ]
}));

// 估值
charts.push(mk('valChart',{
  backgroundColor:'transparent',tooltip:{trigger:'axis'},legend:{data:['PE_TTM','PB'],textStyle:{color:C.sub},top:0},
  grid:{left:56,right:64,top:34,bottom:40},
  xAxis:{type:'category',data:D.val.dates,boundaryGap:false,...axisCommon,axisLabel:{color:C.sub,formatter:v=>v.slice(0,4)+'-'+v.slice(4,6)}},
  yAxis:[
    {type:'value',name:'PE',scale:true,...axisCommon,nameTextStyle:{color:C.sub}},
    {type:'value',name:'PB',scale:true,...axisCommon,nameTextStyle:{color:C.sub}}
  ],
  series:[
    {name:'PE_TTM',type:'line',data:D.val.pe,showSymbol:false,lineStyle:{color:C.accent,width:1.4},itemStyle:{color:C.accent}},
    {name:'PB',type:'line',yAxisIndex:1,data:D.val.pb,showSymbol:false,lineStyle:{color:C.good,width:1.4},itemStyle:{color:C.good}}
  ]
}));

// 破净率
charts.push(mk('brokenChart',{
  backgroundColor:'transparent',tooltip:{trigger:'axis'},title:{text:'破净股占比 %',left:12,top:6,textStyle:{color:C.txt,fontSize:13,fontWeight:600}},
  grid:{left:52,right:20,top:44,bottom:40},
  xAxis:{type:'category',data:D.broken.dates,boundaryGap:false,...axisCommon,axisLabel:{color:C.sub,formatter:v=>v.slice(2,4)+String.fromCharCode(10)+v.slice(4,6)}},
  yAxis:{type:'value',name:'%',...axisCommon,nameTextStyle:{color:C.sub}},
  series:[{name:'破净率',type:'line',data:D.broken.vals,showSymbol:true,symbolSize:4,lineStyle:{color:C.bad,width:2},itemStyle:{color:C.bad},
    areaStyle:{color:'rgba(240,86,75,.12)'},
    markLine:{silent:true,symbol:'none',lineStyle:{color:C.warn,type:'dashed'},data:[{yAxis:8,label:{formatter:'8%',color:C.warn}},{yAxis:10,label:{formatter:'10%',color:C.warn}}]}}]
}));

// 成交额
charts.push(mk('amtChart',{
  backgroundColor:'transparent',tooltip:{trigger:'axis'},title:{text:'成交额20日均 (亿元)',left:12,top:6,textStyle:{color:C.txt,fontSize:13,fontWeight:600}},
  grid:{left:56,right:20,top:44,bottom:40},
  xAxis:{type:'category',data:D.amt.dates,boundaryGap:false,...axisCommon,axisLabel:{color:C.sub,formatter:v=>v.slice(0,4)+'-'+v.slice(4,6)}},
  yAxis:{type:'value',name:'亿元',scale:true,...axisCommon,nameTextStyle:{color:C.sub}},
  series:[{name:'成交额',type:'line',data:D.amt.vals,showSymbol:false,lineStyle:{color:C.accent,width:1.4},itemStyle:{color:C.accent},areaStyle:{color:'rgba(79,140,255,.12)'}}]
}));

// 两融
charts.push(mk('marginChart',{
  backgroundColor:'transparent',tooltip:{trigger:'axis'},title:{text:'融资余额 (亿元)',left:12,top:6,textStyle:{color:C.txt,fontSize:13,fontWeight:600}},
  grid:{left:64,right:24,top:44,bottom:40},
  xAxis:{type:'category',data:D.margin.dates,boundaryGap:false,...axisCommon,axisLabel:{color:C.sub,formatter:v=>v.slice(0,4)+'-'+v.slice(4,6)}},
  yAxis:{type:'value',scale:true,...axisCommon},
  series:[{name:'融资余额',type:'line',data:D.margin.vals,showSymbol:false,lineStyle:{color:C.good,width:1.6},itemStyle:{color:C.good},areaStyle:{color:'rgba(34,211,167,.10)'}}]
}));

// Shibor 短端资金价格
charts.push(mk('shiborChart',{
  backgroundColor:'transparent',tooltip:{trigger:'axis'},legend:{data:['Shibor隔夜','Shibor 1周'],textStyle:{color:C.sub},top:0},
  title:{text:'Shibor 短端资金价格 (%)',left:12,top:6,textStyle:{color:C.txt,fontSize:13,fontWeight:600}},
  grid:{left:52,right:24,top:44,bottom:40},
  xAxis:{type:'category',data:D.shibor.dates,boundaryGap:false,...axisCommon,axisLabel:{color:C.sub,formatter:v=>v.slice(0,4)+'-'+v.slice(4,6)}},
  yAxis:{type:'value',name:'%',scale:true,...axisCommon,nameTextStyle:{color:C.sub}},
  series:[
    {name:'Shibor隔夜',type:'line',data:D.shibor.on,showSymbol:false,lineStyle:{color:C.accent,width:1.5},itemStyle:{color:C.accent}},
    {name:'Shibor 1周',type:'line',data:D.shibor.w1,showSymbol:false,lineStyle:{color:C.warn,width:1.3},itemStyle:{color:C.warn}}
  ]
}));

// M1-M2 剪刀差
charts.push(mk('m1m2Chart',{
  backgroundColor:'transparent',tooltip:{trigger:'axis'},legend:{data:['M1同比','M2同比','M1-M2剪刀差'],textStyle:{color:C.sub},top:0},
  title:{text:'M1-M2 剪刀差 (%)',left:12,top:24,textStyle:{color:C.txt,fontSize:13,fontWeight:600}},
  grid:{left:52,right:20,top:64,bottom:40},
  xAxis:{type:'category',data:D.m1m2.months,...axisCommon,axisLabel:{color:C.sub,formatter:v=>v.slice(2,4)+String.fromCharCode(10)+v.slice(4,6)}},
  yAxis:{type:'value',name:'%',...axisCommon,nameTextStyle:{color:C.sub}},
  series:[
    {name:'M1同比',type:'line',data:D.m1m2.m1,showSymbol:true,symbolSize:4,lineStyle:{color:C.accent,width:1.4},itemStyle:{color:C.accent}},
    {name:'M2同比',type:'line',data:D.m1m2.m2,showSymbol:true,symbolSize:4,lineStyle:{color:C.sub,width:1.2},itemStyle:{color:C.sub}},
    {name:'M1-M2剪刀差',type:'bar',data:D.m1m2.gap,itemStyle:{color:p=>p.value>=0?C.good:C.bad}}
  ]
}));

// 社融增量
charts.push(mk('sfChart',{
  backgroundColor:'transparent',tooltip:{trigger:'axis'},title:{text:'社会融资增量 (亿元/月)',left:12,top:6,textStyle:{color:C.txt,fontSize:13,fontWeight:600}},
  grid:{left:60,right:20,top:44,bottom:40},
  xAxis:{type:'category',data:D.sf.months,...axisCommon,axisLabel:{color:C.sub,formatter:v=>v.slice(2,4)+String.fromCharCode(10)+v.slice(4,6)}},
  yAxis:{type:'value',name:'亿元',...axisCommon,nameTextStyle:{color:C.sub}},
  series:[{name:'社融增量',type:'bar',data:D.sf.inc,itemStyle:{color:'rgba(79,140,255,.75)'}}]
}));
</script>
</body>
</html>
"""

html = (HTML
        .replace("__DATA__", json.dumps(data, ensure_ascii=False))
        .replace("__LAST_DATE__", last_date)
        .replace("__GEN__", data["generated"])
        .replace("__TOTAL__", str(total))
        .replace("__PE_PCT__", f"{pe_pct:.0f}")
        .replace("__PB_PCT__", f"{pb_pct:.0f}"))

with open(OUT_HTML, "w", encoding="utf-8") as f:
    f.write(html)
with open(os.path.join(OUT_DIR, "data.json"), "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"[OK] 看板已生成: {OUT_HTML}")
print(f"[OK] 原始数据:   {os.path.join(OUT_DIR,'data.json')}")
print(f"     数据截至 {last_date} | 信号命中 {hits}/{total} | PE分位 {pe_pct:.0f}% PB分位 {pb_pct:.0f}% | 破净率 {cur_broken:.1f}%")
