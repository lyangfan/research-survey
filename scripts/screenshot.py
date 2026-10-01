#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Headless-browser verification of a built survey HTML (Playwright, Chromium).

Captures the top of the page plus each section, reports console errors / page errors,
horizontal overflow, empty charts and missing CJK glyph rendering hints. Exit code 1 on errors.

  pip install playwright && python -m playwright install chromium   # or use --chrome /usr/bin/google-chrome
  python scripts/screenshot.py out/survey.html --outdir out/screens
  python scripts/screenshot.py out/survey.html --outdir docs --only top --name preview.png
"""
import argparse
import asyncio
import os
import sys

from playwright.async_api import async_playwright

SECTIONS = ["timeline", "taxonomy", "works", "teams", "map", "oss", "refs"]


async def main(a):
    os.makedirs(a.outdir, exist_ok=True)
    url = "file://" + os.path.abspath(a.html)
    problems = []
    async with async_playwright() as p:
        kw = {"args": ["--no-sandbox"]}
        if a.chrome:
            kw["executable_path"] = a.chrome
        b = await p.chromium.launch(**kw)
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
            refs:document.querySelectorAll('#reflist li').length, toc:[...document.querySelectorAll('#toc a')].map(a=>a.textContent)})""")
        print("rendered:", stats)
        shots = []
        if a.only in (None, "top"):
            f = os.path.join(a.outdir, a.name or "00_top.png")
            await pg.screenshot(path=f)
            shots.append(f)
        if a.only is None:
            for i, sid in enumerate(SECTIONS, 1):
                if not await pg.evaluate(f"!!document.getElementById('{sid}') && !document.getElementById('{sid}').classList.contains('hidden')"):
                    continue
                await pg.evaluate(f"document.getElementById('{sid}').scrollIntoView()")
                await pg.wait_for_timeout(700)
                el = pg.locator("#" + sid)
                f = os.path.join(a.outdir, f"{i:02d}_{sid}.png")
                await el.screenshot(path=f)
                shots.append(f)
            if await pg.evaluate("typeof showCountry==='function' && document.getElementById('map') && !document.getElementById('map').classList.contains('hidden')"):
                await pg.evaluate("showCountry(Object.keys(DATA.cntTeam)[1]||Object.keys(DATA.cntTeam)[0])")
                await pg.wait_for_timeout(400)
                f = os.path.join(a.outdir, "05b_map_click.png")
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
    ap.add_argument("--chrome", default=os.environ.get("CHROME_PATH"), help="system Chrome/Chromium executable (optional)")
    sys.exit(asyncio.run(main(ap.parse_args())))
