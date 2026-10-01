#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Headless-browser verification of a built survey HTML (Playwright, Chromium).

Captures the top of the page plus EVERY visible section (summary, scope, timeline, taxonomy,
works, teams, map, portals, oss, trends, caveats, refs — whatever the report contains), reports
console errors / page errors, horizontal overflow, empty charts and missing CJK glyph rendering
hints. Exit code 1 on errors.

Browser (first that works): --chrome PATH / $CHROME_PATH -> Playwright's bundled Chromium (or
headless shell) for the installed playwright version -> any other Chromium revision already in the
Playwright cache ($PLAYWRIGHT_BROWSERS_PATH, ~/.cache/ms-playwright, ~/Library/Caches/ms-playwright,
%LOCALAPPDATA%/ms-playwright) -> a system Chrome/Chromium/Edge -> if none exists, it runs
`python -m playwright install chromium` once and uses the bundled Chromium (disable with
--no-install). So no system Chrome is needed.

Tall sections (long tables, big trees, reference lists) are also captured as viewport-sized
slices (`03_works_p1.png`, `_p2` …) so the text stays readable; --max-slices caps the count.
Scrollable tables (the works table has its own scroll box) are additionally scrolled inside the
container and captured as `NN_works_table_s2.png`, `_s3` … (--table-slices, default 3; 0 = off).

  pip install playwright && python -m playwright install chromium   # optional if Chrome is installed
  python scripts/screenshot.py out/survey.html --outdir out/screens
  python scripts/screenshot.py out/survey.html --outdir docs --only top --name preview.png
"""
import argparse
import asyncio
import glob
import os
import shutil
import subprocess
import sys

from playwright.async_api import async_playwright

CHROME_CANDIDATES = [
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "microsoft-edge", "msedge",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]


def playwright_cached():
    """Chromium / headless-shell executables already downloaded by Playwright (any revision, newest first)."""
    roots = [os.environ.get("PLAYWRIGHT_BROWSERS_PATH"), os.path.expanduser("~/.cache/ms-playwright"),
             os.path.expanduser("~/Library/Caches/ms-playwright"),
             os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright") if os.environ.get("LOCALAPPDATA") else None]
    rels = ["chrome-linux/chrome", "chrome-linux64/chrome", "chrome-mac/Chromium.app/Contents/MacOS/Chromium",
            "chrome-mac-arm64/Chromium.app/Contents/MacOS/Chromium", "chrome-win/chrome.exe", "chrome-win64/chrome.exe",
            "chrome-headless-shell-linux64/chrome-headless-shell", "chrome-linux/headless_shell",
            "chrome-headless-shell-mac-arm64/chrome-headless-shell", "chrome-headless-shell-mac-x64/chrome-headless-shell",
            "chrome-headless-shell-win64/chrome-headless-shell.exe"]
    hits = []
    for root in filter(None, roots):
        if root == "0" or not os.path.isdir(root):
            continue
        for d in glob.glob(os.path.join(root, "chromium*-*")):
            for r in rels:
                f = os.path.join(d, r)
                if os.path.isfile(f) and os.access(f, os.X_OK):
                    rev = int("".join(ch for ch in d.rsplit("-", 1)[-1] if ch.isdigit()) or 0)
                    hits.append((rev, "headless" not in r, f))
    return [f for _, _, f in sorted(hits, reverse=True)]


def find_chrome():
    """First system Chrome/Chromium/Edge found (PATH names, app bundles, Windows paths, snap)."""
    for c in CHROME_CANDIDATES:
        p = shutil.which(c) if os.sep not in c and "\\" not in c else (c if os.path.exists(c) else None)
        if p:
            return p
    for pat in ("/snap/bin/chromium",):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None


def install_bundled():
    """Download Playwright's Chromium for the installed playwright version (one-time, ~150 MB)."""
    print("no browser found -> running `python -m playwright install chromium` (one-time download; --no-install to skip)")
    try:
        r = subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], timeout=900)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError) as e:
        print(f"playwright install failed: {e}")
        return False


async def launch(p, chrome, allow_install=True):
    kw = {"args": ["--no-sandbox"]}
    if chrome:
        print(f"browser: {chrome}")
        return await p.chromium.launch(executable_path=chrome, **kw)
    first_err = ""
    try:
        b = await p.chromium.launch(**kw)
        print("browser: Playwright bundled Chromium")
        return b
    except Exception as e:  # bundled browser not installed (or another revision)
        first_err = str(e).splitlines()[0] if str(e) else type(e).__name__
    for exe in playwright_cached():
        try:
            b = await p.chromium.launch(executable_path=exe, **kw)
            print(f"browser: Playwright-cached Chromium (other revision) {exe}")
            return b
        except Exception:
            continue
    sys_chrome = find_chrome()
    if sys_chrome:
        print(f"browser: bundled Chromium unavailable -> system browser {sys_chrome}")
        return await p.chromium.launch(executable_path=sys_chrome, **kw)
    if allow_install and install_bundled():
        b = await p.chromium.launch(**kw)
        print("browser: Playwright bundled Chromium (just installed)")
        return b
    raise SystemExit("No browser: run `python -m playwright install chromium` or pass --chrome PATH "
                     f"(bundled launch failed: {first_err})")


COUNT_WRAP_JS = "sid => document.querySelectorAll(\"#\" + sid + \" .tbl-wrap\").length"
TABLE_DIMS_JS = "el => ({sh: el.scrollHeight, ch: el.clientHeight, vis: el.offsetParent !== null})"
SET_SCROLL_JS = "(el, y) => { el.scrollTop = y; }"


async def main(a):
    os.makedirs(a.outdir, exist_ok=True)
    url = "file://" + os.path.abspath(a.html)
    problems = []
    async with async_playwright() as p:
        b = await launch(p, a.chrome, not a.no_install)
        pg = await b.new_page(viewport={"width": a.width, "height": a.height}, device_scale_factor=a.scale)
        logs = []
        pg.on("console", lambda m: logs.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
        pg.on("pageerror", lambda e: logs.append(f"PAGEERROR: {e}"))
        await pg.goto(url)
        await pg.wait_for_function("window.__SURVEY_READY__===true", timeout=20000)
        await pg.wait_for_timeout(1500)
        sw = await pg.evaluate("document.documentElement.scrollWidth")
        if sw > a.width + 2:
            problems.append(f"horizontal overflow: scrollWidth={sw}px > viewport {a.width}px")
        # every visible chart container must contain a canvas with non-zero size
        empty = await pg.evaluate("""[...document.querySelectorAll('[_echarts_instance_]')]
            .filter(el=>el.offsetParent!==null && !(el.querySelector('canvas')&&el.querySelector('canvas').width>0))
            .map(el=>el.id)""")
        if empty:
            problems.append(f"empty charts: {empty}")
        stats = await pg.evaluate("""({works:document.querySelectorAll('#wt tbody tr').length,
            teams:document.querySelectorAll('#tgrid .team').length, repos:document.querySelectorAll('#rt tbody tr:not(.det)').length,
            portals:document.querySelectorAll('#pt tbody tr').length,
            refs:document.querySelectorAll('#reflist li').length, toc:[...document.querySelectorAll('#toc a')].map(a=>a.textContent)})""")
        print("rendered:", stats)
        shots = []
        if a.only in (None, "top"):
            f = os.path.join(a.outdir, a.name or "00_top.png")
            await pg.screenshot(path=f)
            shots.append(f)
        if a.only is None:
            sections = await pg.evaluate("[...document.querySelectorAll('main section:not(.hidden)')].map(s=>s.id)")
            for i, sid in enumerate(sections, 1):
                await pg.evaluate(f"document.getElementById('{sid}').scrollIntoView()")
                await pg.wait_for_timeout(600)
                f = os.path.join(a.outdir, f"{i:02d}_{sid}.png")
                await pg.locator("#" + sid).screenshot(path=f)
                shots.append(f)
                # readable viewport-sized slices for tall sections
                box = await pg.evaluate(f"""(()=>{{const r=document.getElementById('{sid}').getBoundingClientRect();
                    return {{x:r.left+scrollX,y:r.top+scrollY,w:r.width,h:r.height}}}})()""")
                if box["h"] > a.height * 1.3 and a.max_slices > 0:
                    y, k = box["y"], 1
                    while y < box["y"] + box["h"] - 20 and k <= a.max_slices:
                        hh = min(a.height, box["y"] + box["h"] - y)
                        fs = os.path.join(a.outdir, f"{i:02d}_{sid}_p{k}.png")
                        await pg.screenshot(path=fs, full_page=True, clip={"x": box["x"], "y": y, "width": box["w"], "height": hh})
                        shots.append(fs)
                        y += a.height
                        k += 1
                # scrollable tables (e.g. the works table, max-height 680px): the section shot only shows the
                # first screen of rows, so scroll inside the container and capture a few more slices
                n_wrap = await pg.evaluate(COUNT_WRAP_JS, sid)
                for t in range(n_wrap if a.table_slices > 0 else 0):
                    loc = pg.locator("#" + sid + " .tbl-wrap").nth(t)
                    dims = await loc.evaluate(TABLE_DIMS_JS)
                    if not dims["vis"] or dims["sh"] <= dims["ch"] + 10:
                        continue
                    step = max(int(dims["ch"] * 0.9), 50)
                    j, top = 1, step
                    while top < dims["sh"] - 10 and j <= a.table_slices:
                        await loc.evaluate(SET_SCROLL_JS, top)
                        await pg.wait_for_timeout(250)
                        suffix = str(t + 1) if n_wrap > 1 else ""
                        fs = os.path.join(a.outdir, f"{i:02d}_{sid}_table{suffix}_s{j + 1}.png")
                        await loc.screenshot(path=fs)
                        shots.append(fs)
                        top += step
                        j += 1
                    await loc.evaluate(SET_SCROLL_JS, 0)
            if await pg.evaluate("typeof showCountry==='function' && document.getElementById('map') && !document.getElementById('map').classList.contains('hidden')"):
                await pg.evaluate("showCountry(Object.keys(DATA.cntTeam)[1]||Object.keys(DATA.cntTeam)[0])")
                await pg.wait_for_timeout(400)
                n = sections.index("map") + 1 if "map" in sections else 0
                f = os.path.join(a.outdir, f"{n:02d}b_map_click.png")
                await pg.locator("#map").screenshot(path=f)
                shots.append(f)
        await b.close()
    errs = [l for l in logs if l.startswith(("error", "PAGEERROR"))]
    print("screenshots:", *shots, sep="\n  ")
    print("console:", "\n  ".join(logs) or "no console errors/warnings")
    for pr in problems:
        print("PROBLEM:", pr)
    return 1 if (errs or problems) else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("html")
    ap.add_argument("--outdir", default="screens")
    ap.add_argument("--only", choices=["top"], help="only the first viewport")
    ap.add_argument("--name", help="file name for --only top")
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--height", type=int, default=1000)
    ap.add_argument("--scale", type=float, default=1)
    ap.add_argument("--max-slices", type=int, default=6, help="max viewport slices per tall section (0 = none)")
    ap.add_argument("--table-slices", type=int, default=3,
                    help="extra slices per scrollable table (scrolled inside the container; 0 = none)")
    ap.add_argument("--chrome", default=os.environ.get("CHROME_PATH"),
                    help="Chrome/Chromium executable (default: bundled Chromium, else cached/system Chrome, else auto-install)")
    ap.add_argument("--no-install", action="store_true", help="never run `playwright install chromium` automatically")
    sys.exit(asyncio.run(main(ap.parse_args())))
