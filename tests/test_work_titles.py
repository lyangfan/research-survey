#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import os
import sys
import tempfile
import textwrap
import unittest

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

try:
    import work_names
except ImportError:
    work_names = None

import build  # noqa: E402

VL = "Virtual lab of artificial intelligence agents accelerating nanobody design against SARS-CoV-2 variants"
SCOUTER = "Scouter predicts transcriptional responses to genetic perturbations with large language model embeddings"
TOWARD = "Toward self-driving laboratory 2.0 for chemistry and materials discovery"


def mid_word(original, result):
    """True when result drops a tail by slicing through a Latin word."""
    if result == original:
        return False
    if not result.endswith("…"):
        return True
    body = result[:-1]
    if not original.startswith(body):
        return True
    rest = original[len(body):]
    if body and rest and body[-1].isalnum() and rest[0].isalnum() and ord(body[-1]) < 128 and ord(rest[0]) < 128:
        return True
    return False


class TruncateWordsTest(unittest.TestCase):
    def test_module_present(self):
        self.assertIsNotNone(work_names, "scripts/work_names.py must define word-boundary shortening")

    def test_sixty_char_slice_is_rejected(self):
        hard = VL[:60]
        self.assertEqual(len(hard), 60)
        self.assertTrue(mid_word(VL, hard), "the [:60] slice of this title cuts inside a word")
        out = work_names.truncate_words(VL, 60)
        self.assertFalse(mid_word(VL, out), out)
        self.assertNotEqual(out, hard)
        self.assertTrue(out.endswith("…"))
        self.assertLessEqual(len(out), 60)

    def test_scouter_sixty(self):
        hard = SCOUTER[:60]
        self.assertTrue(work_names.is_hard_truncated_name(hard, SCOUTER))
        out = work_names.truncate_words(SCOUTER, 60)
        self.assertFalse(mid_word(SCOUTER, out), out)
        self.assertFalse(work_names.is_hard_truncated_name(out, SCOUTER))

    def test_limit_keeps_whole_text(self):
        self.assertEqual(work_names.truncate_words("Virtual Lab", 60), "Virtual Lab")
        self.assertEqual(work_names.truncate_words("SciMON", 4), "SciMON")

    def test_hyphen_is_a_boundary(self):
        out = work_names.truncate_words(TOWARD, 16)
        self.assertFalse(mid_word(TOWARD, out), out)
        self.assertTrue(out.endswith("…"))

    def test_many_limits_never_cut_a_word(self):
        samples = [VL, SCOUTER, TOWARD, "Self-Driving Laboratories for Chemistry and Materials Science",
                   "虚拟实验室加速纳米抗体设计与验证"]
        for text in samples:
            for limit in range(1, len(text) + 3):
                out = work_names.truncate_words(text, limit)
                self.assertFalse(mid_word(text, out), (limit, out))
                if len(text) <= limit:
                    self.assertEqual(out, text)


class HardCutTest(unittest.TestCase):
    def test_detects_uploaded_patterns(self):
        self.assertTrue(work_names.is_hard_truncated_name(VL[:60], VL))
        self.assertTrue(work_names.is_hard_truncated_name("Toward self", TOWARD))
        self.assertTrue(work_names.is_hard_truncated_name(
            "Self", "Self-Driving Laboratories for Chemistry and Materials Science"))
        self.assertTrue(work_names.is_hard_truncated_name(
            "Real", "Real-time experiment-theory closed-loop interaction for autonomous materials science"))
        self.assertTrue(work_names.is_hard_truncated_name("The AI co", "The AI co-scientist is here"))
        self.assertTrue(work_names.is_hard_truncated_name("A Self", "A Self-Driving Lab for Nano- and Advanced Materials Synthesis"))

    def test_keeps_real_short_names(self):
        self.assertFalse(work_names.is_hard_truncated_name(
            "SciMON", "SciMON: Scientific Inspiration Machines Optimized for Novelty"))
        self.assertFalse(work_names.is_hard_truncated_name(
            "CRESt", "A multimodal robotic platform for multi-element electrocatalyst discovery"))
        self.assertFalse(work_names.is_hard_truncated_name(
            "Virtual Lab", "The Virtual Lab of AI agents designs new SARS-CoV-2 nanobodies"))
        self.assertFalse(work_names.is_hard_truncated_name(
            "The Virtual Lab", "The Virtual Lab: AI Agents Design New SARS-CoV-2 Nanobodies with Experimental Validation"))
        self.assertFalse(work_names.is_hard_truncated_name("GeneAgent", "GeneAgent: self-verification language agent"))

    def test_repair_writes_the_full_title_back(self):
        rows = [
            {"name": VL[:60], "title": VL, "url": "https://example.test/vl"},
            {"name": "SciMON", "title": "SciMON: Scientific Inspiration Machines Optimized for Novelty"},
            {"name": "Toward self", "title": TOWARD},
        ]
        fixed, n = work_names.repair_works(rows)
        self.assertEqual(n, 2)
        self.assertEqual(fixed[0]["name"], VL)
        self.assertEqual(fixed[1]["name"], "SciMON")
        self.assertEqual(fixed[2]["name"], TOWARD)
        self.assertEqual(rows[0]["name"], VL[:60])

    def test_display_prefers_title(self):
        self.assertEqual(work_names.work_display_title({"name": "Toward self", "title": TOWARD}), TOWARD)
        self.assertEqual(work_names.work_display_title({"name": "CRESt", "title": "  "}), "CRESt")
        self.assertEqual(work_names.work_display_title({"name": "Only name"}), "Only name")


class TemplateContractTest(unittest.TestCase):
    def test_table_and_country_list_show_title(self):
        with open(os.path.join(ROOT, "scripts", "template.html"), encoding="utf-8") as f:
            html = f.read()
        self.assertIn("function workLabel(", html)
        self.assertIn("${esc(workLabel(w))}", html)
        self.assertNotIn("${esc(w.name)}</a>", html)
        self.assertIn('td class="wn"', html)
        self.assertLess(html.index('td class="wn"'), html.index("${esc(workLabel(w))}"))

    def test_screenshot_checks_full_titles(self):
        with open(os.path.join(ROOT, "scripts", "screenshot.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn("works column missing full title", src)
        self.assertIn("status tag clipped", src)


class CheckWarnTest(unittest.TestCase):
    def test_check_warns_on_midword_name(self):
        build.errors.clear()
        build.warnings.clear()
        meta = {"directions": [{"key": "IDEA", "name": "Ideas"}], "check_date": "2026-10-22"}
        works = [{
            "name": VL[:60], "title": VL, "dirs": ["IDEA"], "date": "2025-01-01",
            "status": "Nature", "peer": True, "url": "https://example.test/vl", "checked": "2026-10-22",
        }]
        build.validate(meta, works, [], [], [], [])
        self.assertFalse(build.errors)
        self.assertTrue(any("hard-cut" in w for w in build.warnings), build.warnings)

    def test_check_silent_for_real_short_name(self):
        build.errors.clear()
        build.warnings.clear()
        meta = {"directions": [{"key": "IDEA", "name": "Ideas"}], "check_date": "2026-10-22"}
        works = [{
            "name": "SciMON", "title": "SciMON: Scientific Inspiration Machines Optimized for Novelty",
            "dirs": ["IDEA"], "date": "2024", "status": "ACL", "peer": True,
            "url": "https://example.test/s", "checked": "2026-10-22",
        }]
        build.validate(meta, works, [], [], [], [])
        self.assertFalse(any("hard-cut" in w for w in build.warnings))


class RenderedTableTest(unittest.TestCase):
    def test_built_page_shows_title_not_the_slice(self):
        if sync_playwright is None:
            self.skipTest("playwright is not installed")
        html_path = _build_fixture()
        with sync_playwright() as p:
            browser = _launch(p)
            if browser is None:
                self.skipTest("no Chromium/Chrome for the works-table check")
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto("file://" + html_path)
            page.wait_for_function("window.__SURVEY_READY__===true", timeout=20000)
            texts = page.eval_on_selector_all("#wt tbody td.wn a.nm", "els => els.map(e => e.textContent)")
            self.assertIn(VL, texts)
            self.assertIn(TOWARD, texts)
            self.assertNotIn(VL[:60], texts)
            self.assertNotIn("Toward self", texts)
            clipped = page.evaluate(textwrap.dedent("""
                () => {
                  const bad = [];
                  for (const a of document.querySelectorAll('#wt tbody td.wn a.nm')) {
                    const cell = a.closest('td');
                    const cs = getComputedStyle(cell), as_ = getComputedStyle(a);
                    if (as_.whiteSpace === 'nowrap') bad.push('nowrap ' + a.textContent.slice(0, 40));
                    if ((cs.overflowY === 'hidden' || cs.overflow === 'hidden') && cell.scrollHeight > cell.clientHeight + 2)
                      bad.push('clip ' + a.textContent.slice(0, 40));
                  }
                  for (const tag of document.querySelectorAll('#wt tbody td.ws .tag')) {
                    const ts = getComputedStyle(tag);
                    if (ts.whiteSpace === 'nowrap' && tag.scrollWidth > tag.clientWidth + 2)
                      bad.push('status ' + tag.textContent.slice(0, 40));
                  }
                  return bad;
                }
            """))
            self.assertEqual(clipped, [])
            status = page.eval_on_selector("#wt tbody td.ws .tag", "el => el.textContent")
            self.assertIn("Nature Computational Science", status)
            browser.close()


def _launch(p):
    try:
        return p.chromium.launch(args=["--no-sandbox"])
    except Exception:
        pass
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        path = _which(name)
        if path:
            try:
                return p.chromium.launch(executable_path=path, args=["--no-sandbox"])
            except Exception:
                continue
    return None


def _which(name):
    for d in os.environ.get("PATH", "").split(os.pathsep):
        p = os.path.join(d, name)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def _build_fixture():
    src = os.path.join(ROOT, "examples", "agent-science-mini")
    tmp = tempfile.mkdtemp(prefix="survey-titles-")
    for name in ("meta.json", "teams.json", "timeline.json", "repos.json"):
        with open(os.path.join(src, name), encoding="utf-8") as f:
            raw = f.read()
        with open(os.path.join(tmp, name), "w", encoding="utf-8") as f:
            f.write(raw)
    os.makedirs(os.path.join(tmp, "narrative"), exist_ok=True)
    for name in ("summary", "scope", "challenges", "caveats"):
        with open(os.path.join(tmp, "narrative", name + ".html"), "w", encoding="utf-8") as f:
            f.write("<p>fixture</p>")
    works = [{
        "name": VL[:60],
        "title": VL,
        "dirs": ["IDEA"],
        "date": "2025-11-01",
        "status": "Nature Computational Science（2025-11-01）同行评审长状态标签不应被裁切",
        "peer": True,
        "url": "https://example.test/virtual-lab",
        "inst": "Stanford",
        "country": "US",
        "contrib": "纳米抗体",
        "checked": "2026-10-22",
    }, {
        "name": "Toward self",
        "title": TOWARD,
        "dirs": ["EXP"],
        "date": "2024-06-01",
        "status": "arXiv 预印本",
        "peer": False,
        "url": "https://example.test/toward",
        "inst": "—",
        "country": "",
        "contrib": "自驱动实验室",
        "checked": "2026-10-22",
    }]
    with open(os.path.join(tmp, "works.json"), "w", encoding="utf-8") as f:
        json.dump(works, f, ensure_ascii=False)
    world = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"ISO_A2": "US", "NAME": "United States"},
            "geometry": {"type": "Polygon", "coordinates": [[[-100, 40], [-90, 40], [-90, 30], [-100, 30], [-100, 40]]]},
        }],
    }
    world_path = os.path.join(tmp, "world.geojson")
    with open(world_path, "w", encoding="utf-8") as f:
        json.dump(world, f)
    out = os.path.join(tmp, "survey.html")
    build.render(tmp, out, world_path, None, True)
    return out


if __name__ == "__main__":
    unittest.main()
