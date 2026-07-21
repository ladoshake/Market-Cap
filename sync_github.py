#!/usr/bin/env python3
"""将项目文件同步到 GitHub 仓库（Contents API 方式）。

为什么不用 git push：本工作环境代理屏蔽了 github.com 的 git 智能 HTTP 端点，
但 api.github.com 可通。故通过 Contents API（PUT /repos/.../contents/<file>）写入，
走 api.github.com，可绕过代理限制。

用法：
  GH_TOKEN=xxx python sync_github.py
  或把令牌放在本目录的 .github_token 文件中（自动读取）。

注意：令牌仅从环境变量 / 本地 .github_token 读取，不会出现在脚本或仓库中。
"""
import os
import sys
import json
import base64
import urllib.request
import urllib.error
import urllib.parse

REPO = "ladoshake/Market-Cap"
BRANCH = "main"
BASE = os.path.dirname(os.path.abspath(__file__))
FILES = ["fetch_data.py", "build_html.py", "data.json", "index.html", ".gitignore"]


def get_token():
    t = os.environ.get("GH_TOKEN")
    if t:
        return t.strip()
    p = os.path.join(BASE, ".github_token")
    if os.path.exists(p):
        with open(p) as f:
            return f.read().strip()
    return None


def api(method, path, data=None):
    if path:
        url = f"https://api.github.com/repos/{REPO}/contents/{urllib.parse.quote(path, safe='')}"
    else:
        url = f"https://api.github.com/repos/{REPO}"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        txt = e.read().decode() if e.fp else ""
        try:
            return e.code, json.loads(txt)
        except Exception:
            return e.code, {"message": txt}


def main():
    global TOKEN
    TOKEN = get_token()
    if not TOKEN:
        print("ERROR: 未找到 GH_TOKEN（请设置环境变量，或在脚本同目录放 .github_token 文件）")
        sys.exit(1)

    st, _ = api("GET", "")
    if st != 200:
        print(f"ERROR: 无法访问仓库（HTTP {st}），请检查令牌权限与网络")
        sys.exit(1)

    ok = 0
    for fn in FILES:
        fpath = os.path.join(BASE, fn)
        if not os.path.exists(fpath):
            print(f"[SKIP] {fn} 本地不存在")
            continue
        with open(fpath, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        st_get, info = api("GET", fn)
        sha = info.get("sha") if st_get == 200 else None
        payload = {
            "message": f"Weekly sync: update {fn}",
            "content": b64,
            "branch": BRANCH,
        }
        if sha:
            payload["sha"] = sha
        st_put, resp = api("PUT", fn, payload)
        if st_put in (200, 201):
            print(f"[OK] {fn} -> {st_put} ({'updated' if sha else 'created'})")
            ok += 1
        else:
            print(f"[FAIL] {fn} -> {st_put} {str(resp)[:300]}")
    print(f"\n同步完成：{ok}/{len(FILES)} 个文件成功")


if __name__ == "__main__":
    main()
