#!/usr/bin/env python3
"""读取 data.json（含 A股/港股/美股 三榜），生成自包含、可交互的 index.html。

- 顶部三个 Tab 切换 A股 / 港股 / 美股
- 概览卡片 + 可点表头排序的明细表，随当前榜单更新
- 市值按本币（亿 / 万亿）展示并带币种；红涨绿跌
- 纯前端、数据内嵌、无 CDN 依赖
"""
import json

DATA = "/Users/green/WorkBuddy/2026-07-21-16-50-33/data.json"
OUT = "/Users/green/WorkBuddy/2026-07-21-16-50-33/index.html"


def main():
    with open(DATA, encoding="utf-8") as f:
        payload = json.load(f)
    data_js = json.dumps(payload, ensure_ascii=False)

    html = TEMPLATE.replace("/*__DATA__*/", data_js)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)

    n = {k: len(v["stocks"]) for k, v in payload["boards"].items()}
    print(f"已生成 {OUT}（A股 {n['A']} / 港股 {n['HK']} / 美股 {n['US']} 只，"
          f"更新于 {payload['updated']}）")


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>A股市值 Top30 排行榜</title>
<style>
  :root{
    --bg:#f5f7fa; --card:#ffffff; --ink:#1f2937; --muted:#6b7280;
    --line:#e5e7eb; --up:#e23c3c; --down:#16a34a; --accent:#2563eb;
    --accent-soft:#dbeafe; --chip:#f1f5f9;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
    background:var(--bg);color:var(--ink);line-height:1.5;padding:16px}
  .wrap{max-width:1100px;margin:0 auto}
  header{margin-bottom:14px}
  h1{font-size:22px;font-weight:700}
  .sub{color:var(--muted);font-size:13px;margin-top:4px}
  /* Tab */
  .tabs{display:flex;gap:8px;margin:14px 0}
  .tab{flex:1;padding:11px 0;text-align:center;border:1px solid var(--line);border-radius:10px;
    background:var(--card);color:var(--muted);font-size:15px;font-weight:600;cursor:pointer;
    transition:.15s;user-select:none}
  .tab:hover{color:var(--ink)}
  .tab.active{background:var(--accent);border-color:var(--accent);color:#fff}
  .panel{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:16px}
  .panel h2{font-size:15px;margin-bottom:12px;font-weight:600}
  /* 工具栏 */
  .toolbar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:12px}
  .count{font-size:13px;color:var(--muted)}
  /* 表格 */
  .tbl-scroll{overflow-x:auto}
  table{width:100%;border-collapse:collapse;font-size:13px}
  th,td{padding:9px 10px;text-align:right;white-space:nowrap;border-bottom:1px solid var(--line)}
  th:first-child,td:first-child,th:nth-child(2),td:nth-child(2),th:nth-child(3),td:nth-child(3){text-align:left}
  thead th{position:sticky;top:0;background:#fafbfc;cursor:pointer;user-select:none;font-weight:600;color:var(--ink)}
  thead th:hover{color:var(--accent)}
  thead th .arrow{font-size:10px;color:var(--muted)}
  tbody tr:hover{background:var(--accent-soft)}
  .up{color:var(--up);font-weight:600}
  .down{color:var(--down);font-weight:600}
  .flat{color:var(--muted)}
  .chip{display:inline-block;background:var(--chip);border-radius:6px;padding:2px 8px;font-size:12px;color:var(--muted)}
  /* 冻结前2列（排名/名称） */
  .tbl-scroll{position:relative}
  .fz{position:sticky;background:var(--card);z-index:2}
  .fz1{left:0;width:48px;min-width:48px}
  .fz2{left:48px;width:120px;min-width:120px;box-shadow:1px 0 0 var(--line)}
  thead th.fz{background:#fafbfc;z-index:3}
  tbody tr:hover .fz{background:var(--accent-soft)}
  footer{color:var(--muted);font-size:12px;text-align:center;padding:18px 0}
  @media(max-width:680px){
    h1{font-size:19px}
    .tab{font-size:14px;padding:10px 0}
  }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>市值 Top30 排行榜</h1>
    <div class="sub" id="sub"></div>
  </header>

  <div class="tabs" id="tabs"></div>

  <div class="panel">
    <h2 id="tblTitle">明细数据</h2>
    <div class="toolbar">
      <span class="count" id="count"></span>
    </div>
    <div class="tbl-scroll">
      <table id="tbl">
        <thead>
          <tr>
            <th data-k="rank" class="fz fz1">排名</th>
            <th data-k="name" class="fz fz2">名称</th>
            <th data-k="code">代码</th>
            <th data-k="price">现价</th>
            <th data-k="pct">涨跌幅</th>
            <th data-k="change">涨跌额</th>
            <th data-k="total_mv">总市值</th>
            <th data-k="pe">市盈率</th>
            <th data-k="board">板块</th>
          </tr>
        </thead>
        <tbody id="tbody"></tbody>
      </table>
    </div>
  </div>

  <footer>数据来源：东方财富 / 新浪财经 / 腾讯证券 · 市值单位为本币（亿 / 万亿）· 仅供参考，不构成投资建议</footer>
</div>

<script>
const PAYLOAD = /*__DATA__*/;
const BOARD_ORDER = ["A","HK","US"];
const CUR_NAME = {CNY:"元", HKD:"港元", USD:"美元"};
let currentBoard = "A";
let sortKey = "rank", sortDir = 1;

const fmtYi = (v, cur) => {
  if (v == null) return "-";
  const c = CUR_NAME[cur] || "";
  return (v >= 10000 ? (v/10000).toFixed(2)+"万亿" : v.toFixed(0)+"亿") + c;
};
const fmtPrice = (v, sym) => v == null ? "-" : sym + v.toFixed(2);
const fmtPct = v => v == null ? "-" : (v>0?"+":"") + v.toFixed(2) + "%";
const cls = v => v == null ? "flat" : (v>0?"up":(v<0?"down":"flat"));

// 副标题
document.getElementById("sub").textContent =
  `更新时间 ${PAYLOAD.updated} · 共三大市场榜单`;

// Tab 渲染
const tabsEl = document.getElementById("tabs");
BOARD_ORDER.forEach(k=>{
  const b = PAYLOAD.boards[k];
  const el = document.createElement("div");
  el.className = "tab" + (k===currentBoard?" active":"");
  el.textContent = b.name;
  el.dataset.k = k;
  el.addEventListener("click", ()=>{
    currentBoard = k; sortKey="rank"; sortDir=1;
    document.querySelectorAll(".tab").forEach(t=>t.classList.remove("active"));
    el.classList.add("active");
    document.querySelectorAll("thead th .arrow").forEach(a=>a.remove());
    render();
  });
  tabsEl.appendChild(el);
});

function board(){ return PAYLOAD.boards[currentBoard]; }

function render(){
  const b = board();
  document.getElementById("tblTitle").textContent = b.name + " · 明细数据";
  let rows = b.stocks.slice();
  rows.sort((a,x)=>{
    let x1=a[sortKey], y1=x[sortKey];
    if(typeof x1==="string"){ return x1.localeCompare(y1,"zh")*sortDir; }
    x1=x1==null?-Infinity:x1; y1=y1==null?-Infinity:y1;
    return (x1-y1)*sortDir;
  });
  const sym = b.symbol, cur = b.currency;
  document.getElementById("tbody").innerHTML = rows.map(s=>`
    <tr>
      <td class="fz fz1">${s.rank}</td>
      <td class="fz fz2">${s.name}</td>
      <td>${s.code}</td>
      <td>${fmtPrice(s.price, sym)}</td>
      <td class="${cls(s.pct)}">${fmtPct(s.pct)}</td>
      <td class="${cls(s.change)}">${s.change==null?"-":(s.change>0?"+":"")+s.change.toFixed(2)}</td>
      <td>${fmtYi(s.total_mv, cur)}</td>
      <td>${s.pe==null?"-":s.pe.toFixed(2)}</td>
      <td><span class="chip">${s.board||"-"}</span></td>
    </tr>`).join("");
  document.getElementById("count").textContent = `共 ${rows.length} 只`;
}

document.querySelectorAll("thead th").forEach(th=>{
  th.addEventListener("click",()=>{
    const k=th.dataset.k;
    if(sortKey===k){ sortDir*=-1; } else { sortKey=k; sortDir = (k==="rank"||k==="code"||k==="name"||k==="board")?1:-1; }
    document.querySelectorAll("thead th .arrow").forEach(a=>a.remove());
    const arrow=document.createElement("span"); arrow.className="arrow"; arrow.textContent= sortDir>0?" ▲":" ▼";
    th.appendChild(arrow);
    render();
  });
});

render();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
