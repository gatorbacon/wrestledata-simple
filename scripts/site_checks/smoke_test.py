#!/usr/bin/env python3
"""
Site smoke test -- run before and after every push to main (TJ, 2026-09-30; rule in CLAUDE.md "Hard Rules").

Opens every page in scripts/site_checks/pages.json in real Chrome (Playwright driving the installed Google Chrome),
at desktop width (1280x900) and phone width (390x844, touch, iPhone user agent), and checks each one:
  * the page loads (HTTP 200)
  * no uncaught JavaScript errors and no console errors from the site's own scripts
  * no failed requests to the site itself (missing data JSON, 404 scripts, ...)
  * the page's content is actually VISIBLE: document.body.innerText (skips hidden elements) is at least min_text
    characters, and every 'expect' selector has at least 'min' visible matches. The 2026-09-30 blank rankings page
    had all its rows built but hidden by CSS -- it fails both checks.
  * phones: no sideways scrolling (page wider than the screen)
Ads and analytics requests are blocked in every run, so tests never register as ad impressions (AdSense) or visits
(Google Analytics).

Targets:
  --target local   serves each site's public folder from this machine (the code about to be pushed). Run BEFORE a push.
  --target live    the real sites. Run AFTER a push; --wait-deploy OLD..NEW first waits until files changed in that
                   commit range are live (Netlify deploy finished; up to 10 min per site; a site with no changed files
                   is not waited for).

Usage:
  .venv/bin/python scripts/site_checks/smoke_test.py --target local
  .venv/bin/python scripts/site_checks/smoke_test.py --target live --wait-deploy c7c0df2f9b..07ea4fa118
  options: --site matsavant|kentuckymat|both (default both)   --page NAME (only pages with that name)
           --override /styles.css=path/to/file (local only: serve that file instead; used to prove a check catches a bug)
Exit code 0 = all passed, 1 = something failed. Screenshots (viewport, every page x width) and report.md go to
mt/site_checks/{timestamp}_{target}/ (gitignored).
"""
import argparse
import hashlib
import http.server
import json
import re
import socketserver
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime
from functools import partial
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG = Path(__file__).resolve().parent / "pages.json"
OUT = ROOT / "mt/site_checks"
UA_DESKTOP = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/140.0.0.0 Safari/537.36")
UA_MOBILE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
             "Version/18.0 Mobile/15E148 Safari/604.1")
VIEWPORTS = {"desktop": dict(viewport={"width": 1280, "height": 900}, user_agent=UA_DESKTOP),
             "mobile": dict(viewport={"width": 390, "height": 844}, user_agent=UA_MOBILE, is_mobile=True,
                            has_touch=True, device_scale_factor=2)}
BLOCK = re.compile(r"googlesyndication|googletagmanager|google-analytics|doubleclick|adservice\.google|"
                   r"adtrafficquality|fundingchoicesmessages|googleads|pagead2", re.I)
IMG = re.compile(r"\.(svg|png|jpe?g|webp|gif|ico)(\?|$)", re.I)
THIRD_PARTY_ERR = re.compile(r"googlesyndication|googletagmanager|google-analytics|doubleclick|adsbygoogle|gtag",
                             re.I)


# ---------------------------------------------------------------- local server
class Quiet(http.server.SimpleHTTPRequestHandler):
    overrides = {}

    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def translate_path(self, path):
        p = path.split("?", 1)[0].split("#", 1)[0]
        if p in self.overrides:
            return str(self.overrides[p])
        return super().translate_path(path)


def serve(directory, overrides):
    handler = partial(type("H", (Quiet,), {"overrides": overrides}), directory=str(directory))
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


# ---------------------------------------------------------------- deploy wait
def wait_deploy(site, cfg, rng, log):
    """Wait until the files changed in commit range `rng` under this site's folder are served live."""
    d = cfg["local_dir"].rstrip("/") + "/"
    files = subprocess.run(["git", "diff", "--name-only", "--diff-filter=AM", rng, "--", d], cwd=ROOT,
                           capture_output=True, text=True, check=True).stdout.split()
    files = [f for f in files if not f.startswith(d + "netlify/")][:3]
    if not files:
        log(f"  {site}: no files changed in {rng} -> no deploy to wait for")
        return True
    new = rng.split("..")[-1]
    want = {f: hashlib.sha256(subprocess.run(["git", "show", f"{new}:{f}"], cwd=ROOT, capture_output=True,
                                             check=True).stdout).hexdigest() for f in files}
    t0 = time.time()
    while time.time() - t0 < 600:
        ok = True
        for f, h in want.items():
            url = cfg["live"] + "/" + f[len(d):] + f"?smoke={int(time.time())}"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA_DESKTOP, "Cache-Control": "no-cache"})
                body = urllib.request.urlopen(req, timeout=20).read()
                ok &= hashlib.sha256(body).hexdigest() == h
            except Exception:
                ok = False
        if ok:
            log(f"  {site}: deploy is live ({int(time.time() - t0)} s; checked {', '.join(f[len(d):] for f in files)})")
            return True
        time.sleep(10)
    log(f"  {site}: deploy NOT live after 10 min (checked {', '.join(f[len(d):] for f in files)})")
    return False


# ---------------------------------------------------------------- one page
def check_page(ctx, base, page_cfg, vp, shot_path):
    problems, warns = [], []
    page = ctx.new_page()
    origin = base.split("://", 1)[1].split("/", 1)[0]
    errors, failed, challenged = [], [], []

    def on_console(msg):
        if msg.type != "error":
            return
        loc = (msg.location or {}).get("url", "") or ""
        text = msg.text
        if (THIRD_PARTY_ERR.search(text + loc) or "net::ERR_BLOCKED_BY_CLIENT" in text or "ERR_FAILED" in text
                or text.startswith("Failed to load resource")):        # reported by the request checks instead
            return
        if loc and origin not in loc:
            return
        errors.append(f"console: {text[:160]}")

    def on_pageerror(exc):
        s = f"{exc}\n{getattr(exc, 'stack', '') or ''}"
        if not THIRD_PARTY_ERR.search(s):
            errors.append(f"JS error: {str(exc)[:160]}")

    def on_response(resp):
        u = resp.url
        if origin in u and resp.status >= 400:
            failed.append(f"{resp.status} {u.split(origin, 1)[1][:120]}")

    def on_requestfailed(req):
        u = req.url
        if "/.netlify/submit-challenge" in u:
            challenged.append(u)
            return
        if origin in u and not BLOCK.search(u) and not (req.failure == "net::ERR_ABORTED" and
                                                          re.search(r"\.pdf(\?|$)", u)):
            failed.append(f"failed ({req.failure}) {u.split(origin, 1)[1][:120]}")

    page.on("console", on_console)
    page.on("pageerror", on_pageerror)
    page.on("request", lambda r: challenged.append(r.url) if "/.netlify/submit-challenge" in r.url else None)
    page.on("response", on_response)
    page.on("requestfailed", on_requestfailed)
    url = base + page_cfg["path"]
    try:
        resp = page.goto(url, wait_until="load", timeout=45000)
        if resp is None or resp.status != 200:
            problems.append(f"HTTP {resp.status if resp else 'no response'}")
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        page.wait_for_timeout(600)
        for ex in page_cfg.get("expect", []):
            if (ex.get("desktop") and vp != "desktop") or (ex.get("mobile") and vp != "mobile"):
                continue
            need = ex.get("min", 1)
            try:
                page.wait_for_function(
                    "([s, n]) => [...document.querySelectorAll(s)].filter(e => e.offsetWidth > 0 && "
                    "e.offsetHeight > 0 && getComputedStyle(e).visibility !== 'hidden').length >= n",
                    arg=[ex["sel"], need], timeout=6000)
            except Exception:
                got = page.evaluate(
                    "s => [...document.querySelectorAll(s)].filter(e => e.offsetWidth > 0 && e.offsetHeight > 0 && "
                    "getComputedStyle(e).visibility !== 'hidden').length", ex["sel"])
                total = page.evaluate("s => document.querySelectorAll(s).length", ex["sel"])
                problems.append(f"'{ex['sel']}': {got} visible (need {need}; {total} in the page)")
        info = page.evaluate("() => ({text: document.body ? document.body.innerText.trim().length : 0, "
                             "sw: document.documentElement.scrollWidth, w: window.innerWidth})")
        if info["text"] < page_cfg.get("min_text", 200):
            problems.append(f"only {info['text']} characters of visible text (need {page_cfg.get('min_text', 200)})")
        if vp == "mobile" and info["sw"] > info["w"] + 2:
            msg = f"scrolls sideways on phones (page {info['sw']}px wide, screen {info['w']}px)"
            (warns if page_cfg.get("known_overflow") else problems).append(msg + (" [known]" if page_cfg.get("known_overflow") else ""))
        page.screenshot(path=str(shot_path))
    except Exception as e:
        problems.append(f"page did not load: {str(e).splitlines()[0][:160]}")
    finally:
        page.close()
    if challenged:
        # Netlify's bot protection answered 403 + a challenge; the browser solved it and loaded the real page. Real
        # visitors get the page directly (checked with curl 2026-09-30), so this is not a failure if the content
        # checks above passed.
        path = page_cfg["path"].split("?")[0]
        problems = [p for p in problems if p != "HTTP 403"]
        failed = [f for f in failed if not (f.startswith("403 ") and f.split(" ", 1)[1].split("?")[0] == path)]
        warns.append("Netlify bot challenge shown to the test browser first (passed; the page then loaded)")
    img = [f for f in dict.fromkeys(failed) if IMG.search(f)]
    other = [f for f in dict.fromkeys(failed) if not IMG.search(f)]
    problems += list(dict.fromkeys(errors))[:5] + [f"request {f}" for f in other[:5]]
    if img:            # a missing picture doesn't break the page (pages fall back / hide it): warn, don't block
        warns.append(f"{len(img)} missing image(s): " + ", ".join(f.split(" ", 1)[-1] for f in img[:6]) +
                     (" ..." if len(img) > 6 else ""))
    return problems, warns


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["local", "live"], required=True)
    ap.add_argument("--site", choices=["matsavant", "kentuckymat", "both"], default="both")
    ap.add_argument("--page", action="append")
    ap.add_argument("--wait-deploy", metavar="OLD..NEW")
    ap.add_argument("--override", action="append", default=[], help="local only: /url/path=local/file")
    a = ap.parse_args()
    cfg = json.loads(CONFIG.read_text())["sites"]
    sites = list(cfg) if a.site == "both" else [a.site]
    out = OUT / f"{datetime.now():%Y-%m-%d_%H%M%S}_{a.target}"
    out.mkdir(parents=True, exist_ok=True)
    lines = []

    def log(s):
        print(s, flush=True)
        lines.append(s)

    log(f"Smoke test -- {a.target} -- {datetime.now():%Y-%m-%d %H:%M} -- commit "
        f"{subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=ROOT, capture_output=True, text=True).stdout.strip()}")
    if a.target == "live" and a.wait_deploy:
        log("Waiting for Netlify deploys:")
        for s in sites:
            if not wait_deploy(s, cfg[s], a.wait_deploy, log):
                log("FAILED: deploy not live -- the tests below may be checking the OLD site")
    fails = warns_n = total = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        for s in sites:
            c = cfg[s]
            srv = None
            if a.target == "local":
                ov = {k: (ROOT / v).resolve() for k, v in (o.split("=", 1) for o in a.override)}
                srv, base = serve(ROOT / c["local_dir"], ov)
            else:
                base = c["live"]
            log(f"\n{s}  ({base})")
            for vp, opts in VIEWPORTS.items():
                ctx = browser.new_context(**opts)
                ctx.route(BLOCK, lambda route: route.abort())
                for pc in c["pages"]:
                    if a.page and pc["name"] not in a.page:
                        continue
                    total += 1
                    probs, warns = check_page(ctx, base, pc, vp, out / f"{s}_{pc['name']}_{vp}.png")
                    status = "FAIL" if probs else ("warn" if warns else "ok  ")
                    fails += bool(probs)
                    warns_n += bool(warns)
                    log(f"  {status}  {vp:7s}  {pc['name']:18s} {pc['path']}")
                    for p in probs:
                        log(f"          - {p}")
                    for w in warns:
                        log(f"          - (warning) {w}")
                ctx.close()
            if srv:
                srv.shutdown()
        browser.close()
    log(f"\n{total - fails} of {total} page checks passed" + (f", {fails} FAILED" if fails else "") +
        (f", {warns_n} with warnings (not blocking)" if warns_n else "") + f".  Screenshots + report: {out.relative_to(ROOT)}/")
    (out / "report.md").write_text("```\n" + "\n".join(lines) + "\n```\n")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
