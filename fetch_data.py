#!/usr/bin/env python3
"""抓取 A股 / 港股 / 美股 市值 Top30，输出 data.json（数据内嵌，无外部依赖）。

数据来源（均经沙箱代理可达）：
- A股 : 东方财富数据中心 datacenter-web.eastmoney.com 估值分析报表（总市值，单位 元/CNY）
- 美股 : 新浪 US_CategoryService.getList（含 mktcap，单位 美元/USD），按市值降序
- 港股 : 新浪港股全量代码 + 腾讯 qt.gtimg.cn 批量行情（市值单位 亿港元/HKD）

代理偶发抖动，所有请求均带重试。
"""
import json
import time
import requests

DC = "https://datacenter-web.eastmoney.com/api/data/v1/get"
SINA_US = "http://stock.finance.sina.com.cn/usstock/api/jsonp.php"
SINA_HK = "http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHKStockData"
GTIMG = "https://qt.gtimg.cn/q="
OUT = "/Users/green/WorkBuddy/2026-07-21-16-50-33/data.json"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")

_S = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_$'


# ---------- 基础工具 ----------
def _r64(s, b):
    return ((s | (s << 6)) >> (b % 6)) & 63


def sina_hash(s):
    """移植自 akshare cons.js_hash_text 的 Sina 接口哈希函数。"""
    a = []; c = []
    for i in range(len(s)):
        c0 = ord(s[i])
        if c0 & ~255:
            c0 = ((c0 >> 8) ^ c0) & 0xFFFF
        c.append(c0)
        if len(c) == 3 or i == len(s) - 1:
            while len(c) < 3:
                c.append(0)
            a.append((c[0] >> 2) & 63)
            a.append(((c[1] >> 4) | (c[0] << 6)) & 63)
            a.append(((c[1] << 4) | (c[2] >> 2)) & 63)
            a.append(c[2] & 63)
            c = []
    while len(a) < 16:
        a.append(0)
    r = 0
    for i in range(len(a)):
        r ^= (_r64(a[i] ^ (r | i), i) ^ _r64(i, r)) & 63
    for i in range(len(a)):
        a[i] = (_r64((r | (i & a[i])), r) ^ a[i]) & 63
        r += a[i]
    for i in range(16, len(a)):
        a[i % 16] ^= (a[i] + (i >> 4)) & 63
    for i in range(16):
        a[i] = _S[a[i]]
    return ''.join(a[:16])


def get_text(url, params=None, tries=6, timeout=15):
    last = None
    for _ in range(tries):
        try:
            r = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": UA})
            if r.status_code == 200 and r.text.strip():
                return r.text
        except Exception as e:
            last = e
        time.sleep(1)
    raise last or RuntimeError(f"request failed: {url}")


def to_float(x):
    try:
        if x in (None, "", "-"):
            return None
        return float(x)
    except Exception:
        return None


# ---------- A股 ----------
def fetch_a_share():
    # 1) 最新交易日
    td = json.loads(get_text(DC, {
        "reportName": "RPT_VALUEANALYSIS_DET", "columns": "TRADE_DATE",
        "pageSize": "1", "sortColumns": "TRADE_DATE", "sortTypes": "-1",
        "source": "WEB", "client": "WEB", "p": "1",
    }))
    maxdate = td["result"]["data"][0]["TRADE_DATE"][:10]

    # 2) 总市值前 30
    cols = ("SECURITY_CODE,SECURITY_NAME_ABBR,TRADE_DATE,CLOSE_PRICE,CHANGE_RATE,"
            "TOTAL_MARKET_CAP,NOTLIMITED_MARKETCAP_A,PE_TTM,PB_MRQ")
    d = json.loads(get_text(DC, {
        "reportName": "RPT_VALUEANALYSIS_DET", "columns": cols,
        "pageSize": "30", "sortColumns": "TOTAL_MARKET_CAP", "sortTypes": "-1",
        "filter": f"(TRADE_DATE='{maxdate}')",
        "source": "WEB", "client": "WEB", "p": "1",
    }))
    rows = d["result"]["data"]
    recs = []
    for i, row in enumerate(rows, 1):
        code = str(row["SECURITY_CODE"])
        price = to_float(row.get("CLOSE_PRICE"))
        pct = to_float(row.get("CHANGE_RATE"))
        change = None
        if price is not None and pct is not None and (1 + pct / 100) != 0:
            change = round(price - price / (1 + pct / 100), 2)
        recs.append({
            "rank": i, "code": code, "name": row["SECURITY_NAME_ABBR"],
            "price": price, "pct": pct, "change": change,
            "total_mv": to_float(row.get("TOTAL_MARKET_CAP")) / 1e8,   # 元 -> 亿 CNY
            "float_mv": to_float(row.get("NOTLIMITED_MARKETCAP_A")) / 1e8,
            "pe": to_float(row.get("PE_TTM")), "pb": to_float(row.get("PB_MRQ")),
            "board": board_of(code),
        })
    return recs


def board_of(code):
    if code[:3] in ("688", "689"):
        return "科创板"
    if code[0] in ("8", "4") or code[:3] == "920":
        return "北交所"
    if code[:2] == "60":
        return "沪市主板"
    if code[:2] == "30":
        return "创业板"
    if code[:2] in ("00", "001", "002", "003") or code[:2] == "9":
        return "深市主板"
    return "其他"


# ---------- 美股 ----------
def fetch_us():
    recs = []
    seen = set()
    for page in (1, 2):  # num=20 -> 前两页覆盖前 40，取前 30
        s = f"US_CategoryService.getList?page={page}&num=20&sort=mktcap&asc=0&market=&id="
        url = SINA_US + "/IO.XSRV2.CallbackList[" + sina_hash(s) + "]/US_CategoryService.getList"
        txt = get_text(url, params={"page": str(page)})
        j = json.loads(txt[txt.find("({") + 1: txt.rfind(");")])
        for x in (j.get("data") or []):
            sym = x.get("symbol")
            if not sym or sym in seen:
                continue
            mv = to_float(x.get("mktcap"))
            if mv is None or mv <= 0:
                continue
            seen.add(sym)
            recs.append({
                "rank": 0, "code": sym,
                "name": x.get("cname") or x.get("name") or sym,
                "price": to_float(x.get("price")),
                "pct": to_float(x.get("chg")),
                "change": to_float(x.get("diff")),
                "total_mv": mv / 1e8,            # USD -> 亿 USD
                "float_mv": None,
                "pe": to_float(x.get("pe")),
                "pb": None,
                "board": us_market(x.get("market")),
            })
    recs.sort(key=lambda r: r["total_mv"], reverse=True)
    for i, r in enumerate(recs[:30], 1):
        r["rank"] = i
    return recs[:30]


def us_market(m):
    return {"NASDAQ": "纳斯达克", "NYSE": "纽交所", "AMEX": "美交所"}.get(m, m or "美股")


# ---------- 港股 ----------
def fetch_hk():
    # 1) 新浪取全量港股代码（每页 60，翻页直到为空）
    symbols = []
    page = 1
    while True:
        txt = get_text(SINA_HK, params={
            "page": str(page), "num": "60", "sort": "symbol", "asc": "1",
            "node": "qbgg_hk", "_s_r_a": "page"})
        try:
            arr = json.loads(txt)
        except Exception:
            arr = []
        if not arr:
            break
        symbols.extend(x["symbol"] for x in arr)
        if len(arr) < 60:
            break
        page += 1
        if page > 80:   # 安全阀
            break

    # 2) 腾讯 qt.gtimg.cn 批量取市值（每批 80）
    def parse_gt(line):
        parts = line.split('"')
        if len(parts) < 2:
            return None, None
        code = parts[0].split('v_')[-1].rstrip('= ').strip()  # v_hk00700= -> hk00700
        return code, parts[1].split('~')

    cap_map = {}
    for i in range(0, len(symbols), 80):
        batch = symbols[i:i + 80]
        q = ",".join("hk" + s for s in batch)   # 形如 hk00001,hk00002
        txt = get_text(GTIMG + q)
        for line in txt.strip().split(";"):
            line = line.strip()
            if not line or "=" not in line:
                continue
            try:
                code, f = parse_gt(line)
                # 字段 44/45 为总市值（亿港元）；f[1] 为名称（含 -T/-R 后缀）
                mv = to_float(f[44]) if f and len(f) > 44 else None
                nm = f[1] if f and len(f) > 1 else None
                if mv and mv > 0:
                    cap_map[code[2:]] = (mv, nm)   # hk00700 -> 00700
            except Exception:
                continue

    # 3) 组装并按市值排序取前 30
    recs = []
    for code in symbols:
        tup = cap_map.get(code)
        if not tup:
            continue
        mv, nm = tup
        recs.append({
            "rank": 0, "code": code, "name": nm,  # 名称已从腾讯字段取得
            "price": None, "pct": None, "change": None,
            "total_mv": mv, "float_mv": None,
            "pe": None, "pb": None,
            "board": "创业板" if code.startswith("8") else "主板",
            "_gt": "hk" + code,
        })
    recs.sort(key=lambda r: r["total_mv"], reverse=True)
    # 剔除场外交易(-T)与人民币柜台(-R)股票，仅保留港币主柜台
    recs = [r for r in recs
            if not (r["name"] or "").endswith(("-T", "-R"))
            and not (r["code"] or "").endswith(("-T", "-R"))]
    top = recs[:30]

    # 4) 补全名称/价格/涨跌幅（再批量取一次）
    q = ",".join(r["_gt"] for r in top)
    txt = get_text(GTIMG + q)
    info = {}
    for line in txt.strip().split(";"):
        line = line.strip()
        if not line or "=" not in line:
            continue
        try:
            code, f = parse_gt(line)
            info[code] = f
        except Exception:
            continue
    for i, r in enumerate(top, 1):
        f = info.get(r["_gt"], [])
        if f and len(f) > 1:
            r["name"] = f[1]
            r["price"] = to_float(f[3])
            r["pct"] = to_float(f[32])
            chg = to_float(f[31])
            r["change"] = chg
            r["pe"] = to_float(f[39]) if len(f) > 39 and f[39] not in ("", "0") else None
        else:
            r["name"] = r["code"]
        r["rank"] = i
        r.pop("_gt", None)
    return top


def main():
    print("抓取 A股 ...")
    a = fetch_a_share()
    print(f"  A股 {len(a)} 只，榜首 {a[0]['name']} {a[0]['total_mv']/10000:.2f}万亿")
    print("抓取 美股 ...")
    us = fetch_us()
    print(f"  美股 {len(us)} 只，榜首 {us[0]['name']} {us[0]['total_mv']/10000:.2f}万亿美元")
    print("抓取 港股 ...")
    hk = fetch_hk()
    print(f"  港股 {len(hk)} 只，榜首 {hk[0]['name']} {hk[0]['total_mv']/10000:.2f}万亿港元")

    payload = {
        "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "boards": {
            "A": {"name": "A股", "currency": "CNY", "symbol": "¥", "stocks": a},
            "HK": {"name": "港股", "currency": "HKD", "symbol": "HK$", "stocks": hk},
            "US": {"name": "美股", "currency": "USD", "symbol": "$", "stocks": us},
        },
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\n已写入 {OUT}")


if __name__ == "__main__":
    main()
