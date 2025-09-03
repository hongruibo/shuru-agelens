import re, io, sys, json, urllib.parse, requests
from collections import Counter, deque
from bs4 import BeautifulSoup
import streamlit as st
from fpdf import FPDF

UA = "InfraJoy-Shuru-AgeLens/1.0 (Python)"

# ---------- Utility ----------
def fetch_html(url: str, timeout=20) -> str:
    headers = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"}
    r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text

def domain(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower()

def abs_url(base: str, href: str) -> str:
    return urllib.parse.urljoin(base, href)

def textify(node) -> str:
    return re.sub(r"\s+", " ", (node.get_text() if node else "")).strip()

def count_syllables(word: str) -> int:
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w: return 0
    w = re.sub(r"e$", "", w)
    groups = re.findall(r"[aeiouy]+", w)
    return max(1, len(groups))

def flesch(text: str) -> float:
    sentences = max(1, len(re.findall(r"[.!?]+", text)))
    words = [w for w in re.split(r"\s+", text) if w]
    wc = max(1, len(words))
    syll = sum(count_syllables(w) for w in words)
    wps = wc / sentences
    spw = syll / wc
    score = 206.835 - 1.015 * wps - 84.6 * spw
    return max(0, min(120, score))

# ---------- Core audit on a single page ----------
def audit_page(url: str):
    html = fetch_html(url)
    soup = BeautifulSoup(html, "lxml")

    body_text = textify(soup.body or soup)
    word_count = len(body_text.split())

    # Structure & nav
    headings = soup.select("h1, h2, h3, h4, h5, h6")
    h_levels = [int(h.name[1]) for h in headings]
    has_h1 = bool(soup.select("h1"))
    jumps = sum(1 for i in range(1, len(h_levels)) if h_levels[i] - h_levels[i-1] > 1)

    has_skip = any(
        ("#" in (a.get("href") or "")) and
        (re.search(r"(content|main|skip)", a.get("href") or "", re.I) or re.search(r"skip", textify(a), re.I))
        for a in soup.select("a")
    )
    # Landmarks
    landmark_count = sum(bool(soup.select(sel)) for sel in [
        "main,[role=main]",
        "nav,[role=navigation]",
        "header,[role=banner]",
        "footer,[role=contentinfo]",
    ])

    # Readability
    reading_ease = flesch(body_text)
    avg_sentence_len = len(body_text.split()) / max(1, len(re.findall(r"[.!?]+", body_text)))
    long_paras = sum(1 for p in soup.select("p") if len(textify(p).split()) >= 120)

    # Visual alternatives
    imgs = soup.select("img")
    with_alt = sum(1 for img in imgs if isinstance(img.get("alt"), str) and img.get("alt").strip())
    img_alt_coverage = 1.0 if len(imgs) == 0 else with_alt/len(imgs)

    # Controls & forms
    interactive = soup.select("button, [role=button], a[role=button]")
    unlabeled_buttons = sum(1 for el in interactive if not textify(el) and not (el.get("aria-label") or "").strip())

    form_inputs = soup.select("input,select,textarea")
    def input_unlabeled(el):
        t = (el.get("type") or "").lower()
        if t == "hidden": return False
        _id = el.get("id") or ""
        aria = (el.get("aria-label") or el.get("aria-labelledby") or "").strip()
        has_for = _id and soup.select_one(f'label[for="{_id}"]')
        wrapped = el.find_parent("label") is not None
        return not (has_for or wrapped or aria)
    unlabeled_inputs = sum(1 for el in form_inputs if input_unlabeled(el))

    # Input type hygiene for older users (mobile KB & validation)
    input_types = Counter((el.get("type") or "").lower() for el in soup.select("input"))
    missing_email_type = any((el.get("type") or "").lower() != "email" and re.search(r"email", (el.get("name") or "") + (el.get("id") or ""), re.I) for el in soup.select("input"))
    missing_tel_type = any((el.get("type") or "").lower() != "tel" and re.search(r"(phone|tel)", (el.get("name") or "") + (el.get("id") or ""), re.I) for el in soup.select("input"))

    # Autocomplete hints help memory/typing
    missing_autocomplete = sum(1 for el in soup.select("input,select,textarea") if not (el.get("autocomplete") or "").strip())

    # Viewport & zoom
    viewport_el = soup.select_one('meta[name=viewport]')
    viewport = (viewport_el.get("content") if viewport_el else "") or ""
    viewport_meta = bool(viewport_el)
    viewport_blocks_zoom = bool(re.search(r"user-scalable\s*=\s*no", viewport, re.I) or re.search(r"maximum-scale\s*=\s*1(\.0+)?", viewport, re.I))

    # Links & clarity
    vague_set = {"click here","here","read more","learn more","more","this","link"}
    links = soup.select("a[href]")
    total_links = len(links)
    vague_links = 0
    external_no_warn = 0
    for a in links:
        label = textify(a).lower()
        if label in vague_set: vague_links += 1
        href = a.get("href") or ""
        if href.startswith("http") and domain(href) and domain(href) != domain(url):
            # very light "warn" heuristic: add rel or clear label
            rel = (a.get("rel") or [])
            has_warn = ("noopener" in rel) or ("noreferrer" in rel)
            if not has_warn: external_no_warn += 1

    # Age-friendly discoverability (contact)
    has_tel_link = any(re.match(r"tel:\+?\d", (a.get("href") or ""), re.I) for a in links)
    has_mailto = any((a.get("href") or "").lower().startswith("mailto:") for a in links)
    has_contact_word = re.search(r"\b(contact|support|help|call us|phone)\b", body_text, re.I) is not None

    # Annoyance sniff (very light): captcha or "I am not a robot" text, or age-gate words
    has_captcha_text = re.search(r"captcha|i am not a robot", body_text, re.I) is not None
    has_age_gate_words = re.search(r"\b(enter your age|over 18|date of birth)\b", body_text, re.I) is not None

    # Category subscores (0..100)
    heading_score = (60 if has_h1 else 0) + max(0, 40 - min(4, jumps)*10)
    structure_nav = 0.4*(100 if has_skip else 0) + 0.4*heading_score + 0.2*min(100, (landmark_count/4)*100)
    text_readability = max(0, min(100, reading_ease))
    visual_alternatives = img_alt_coverage*100
    controls_forms = max(0, 100 - (0.6*min(100,unlabeled_buttons*5) + 0.4*min(100,unlabeled_inputs*5)))
    mobile_zoom = 0.6*(100 if viewport_meta else 0) + 0.4*(0 if viewport_blocks_zoom else 100)
    link_clarity = 100 if total_links==0 else max(0, 100 - (vague_links/total_links)*100)

    # Age-friendly extras (advisory bucket)
    discoverability = 0
    discoverability += 35 if has_tel_link else 0
    discoverability += 25 if has_mailto else 0
    discoverability += 40 if has_contact_word else 0
    discoverability = min(100, discoverability)
    hygiene = 100
    if missing_email_type: hygiene -= 15
    if missing_tel_type: hygiene -= 15
    hygiene -= min(40, missing_autocomplete*2)
    hygiene = max(0, hygiene)
    annoyance = 100
    if has_captcha_text: annoyance -= 20
    if has_age_gate_words: annoyance -= 10
    annoyance = max(0, annoyance)

    # Overall Shuru score (weighted)
    score = round(
        0.18*structure_nav +
        0.20*text_readability +
        0.15*visual_alternatives +
        0.20*controls_forms +
        0.12*mobile_zoom +
        0.10*link_clarity +
        0.05*discoverability
    )

    checks = dict(
        wordCount=word_count,
        readingEase=reading_ease,
        avgSentence=avg_sentence_len,
        longParagraphs=long_paras,
        hasH1=has_h1,
        headingJumps=jumps,
        hasSkipLink=has_skip,
        landmarkCount=landmark_count,
        imgAltCoverage=img_alt_coverage,
        unlabeledButtons=unlabeled_buttons,
        unlabeledInputs=unlabeled_inputs,
        inputTypes=dict(input_types),
        missingEmailType=missing_email_type,
        missingTelType=missing_tel_type,
        missingAutocomplete=missing_autocomplete,
        viewportMeta=viewport_meta,
        viewportBlocksZoom=viewport_blocks_zoom,
        totalLinks=total_links,
        vagueLinks=vague_links,
        externalNoWarn=external_no_warn,
        hasTelLink=has_tel_link,
        hasMailto=has_mailto,
        hasContactWord=has_contact_word,
        hasCaptchaText=has_captcha_text,
        hasAgeGateWords=has_age_gate_words,
    )
    breakdown = dict(
        structureNav=structure_nav,
        textReadability=text_readability,
        visualAlternatives=visual_alternatives,
        controlsForms=controls_forms,
        mobileZoom=mobile_zoom,
        linkClarity=link_clarity,
        discoverability=discoverability,
        hygiene=hygiene,
        annoyance=annoyance
    )

    # Recommendations (PM-ready)
    recs = []
    if not has_skip: recs.append("Add a visible 'Skip to content' link (WCAG 2.4.1).")
    if not has_h1: recs.append("Add a single, descriptive H1.")
    if jumps>0: recs.append(f"Fix heading hierarchy (avoid jumps; {jumps} jump{'s' if jumps!=1 else ''}).")
    if landmark_count<3: recs.append("Include landmarks: <main>, <nav>, <header>, <footer>.")
    if img_alt_coverage<1: recs.append(f"Add alt text (~{round((1-img_alt_coverage)*100)}% missing) (WCAG 1.1.1).")
    if unlabeled_buttons>0: recs.append(f"Label buttons/controls ({unlabeled_buttons} unlabeled) (WCAG 4.1.2).")
    if unlabeled_inputs>0: recs.append(f"Associate labels with inputs ({unlabeled_inputs} unlabeled) (WCAG 3.3.2).")
    if not viewport_meta: recs.append("Add responsive viewport meta (WCAG 1.4.10).")
    if viewport_blocks_zoom: recs.append("Allow pinch-zoom (remove user-scalable=no / maximum-scale=1) (WCAG 1.4.4).")
    if reading_ease<60: recs.append(f"Simplify copy; Flesch {round(reading_ease)} (target 60–70).")
    if vague_links>0: recs.append(f"Replace vague link text ({vague_links}) with descriptive labels (WCAG 2.4.4).")
    if not has_tel_link: recs.append("Expose a tap-to-call link (tel:+…).")
    if not has_mailto: recs.append("Expose a mailto: support link or contact form.")
    if missing_email_type: recs.append("Use <input type='email'> for email fields (mobile keyboard).")
    if missing_tel_type: recs.append("Use <input type='tel'> for phone fields (dial pad).")
    if missing_autocomplete>0: recs.append("Add autocomplete hints (name, email, address, etc.).")
    if external_no_warn>0: recs.append("Mark external links with rel=noopener and/or clear labels.")
    if has_captcha_text: recs.append("Offer accessible alternatives to CAPTCHAs.")
    if has_age_gate_words: recs.append("Age-gates: use clear language and alternatives for date input.")

    return dict(url=url, score=score, checks=checks, breakdown=breakdown, recommendations=recs)

# ---------- Mini crawler (optional N pages on same domain) ----------
def crawl_start(url: str, limit: int = 3):
    seen = set([url])
    q = deque([url])
    host = domain(url)
    pages = []
    while q and len(pages) < limit:
        u = q.popleft()
        try:
            res = audit_page(u)
            pages.append(res)
            # enqueue more same-domain links
            html = fetch_html(u)
            soup = BeautifulSoup(html, "lxml")
            for a in soup.select("a[href]"):
                href = a.get("href") or ""
                if href.startswith("#"): continue
                v = abs_url(u, href)
                if domain(v) == host and v not in seen:
                    seen.add(v)
                    q.append(v)
        except Exception:
            continue
    return pages

# ---------- PDF / CSV ----------
def to_csv(pages: list[dict]) -> bytes:
    # Flatten into tickets from recommendations
    rows = ["URL,Priority,Recommendation,Acceptance Criteria"]
    for p in pages:
        for r in p["recommendations"]:
            prio = "High" if ("zoom" in r.lower() or "captcha" in r.lower() or "labels" in r.lower()) else "Medium"
            ac = "Re-run Shuru; issue no longer triggers and page passes associated rule."
            def esc(s): return '"' + s.replace('"','""') + '"'
            rows.append(",".join([esc(p["url"]), esc(prio), esc(r), esc(ac)]))
    return ("\n".join(rows)).encode("utf-8")

def to_pdf(pages: list[dict]) -> bytes:
    pdf = FPDF()
    for idx, p in enumerate(pages):
        pdf.add_page()
        pdf.set_font("Helvetica","",16)
        title = "InfraJoy Labs: Shuru AgeLens — Audit Report"
        if idx>0: title += f" (page {idx+1})"
        pdf.cell(0,10,title, ln=1)
        pdf.set_font("Helvetica","",12)
        pdf.cell(0,8,f"URL: {p['url']}", ln=1)
        pdf.cell(0,8,f"Score: {p['score']}", ln=1)
        pdf.ln(2)
        pdf.set_font("Helvetica","B",12); pdf.cell(0,8,"Breakdown", ln=1)
        pdf.set_font("Helvetica","",12)
        for k,v in p["breakdown"].items():
            pdf.cell(0,7,f"- {k}: {round(v)}", ln=1)
        pdf.ln(2)
        pdf.set_font("Helvetica","B",12); pdf.cell(0,8,"Top recommendations", ln=1)
        pdf.set_font("Helvetica","",12)
        if p["recommendations"]:
            for i, r in enumerate(p["recommendations"][:15], start=1):
                pdf.multi_cell(0,6,f"{i}. {r}")
        else:
            pdf.cell(0,7,"No blocking issues detected.", ln=1)
    return pdf.output(dest="S").encode("latin-1","ignore")

# ---------- UI ----------
st.set_page_config(page_title="InfraJoy Labs: Shuru AgeLens", page_icon="🧭", layout="centered")
st.title("InfraJoy Labs: Shuru AgeLens")
st.write("Paste a URL to get an **age-inclusive UX** audit (WCAG-aligned) with PM-ready tasks. Optionally crawl a few same-domain pages.")

with st.container():
    url = st.text_input("URL to audit", value="https://example.com")
    crawl_n = st.slider("Pages to crawl (same domain)", 1, 5, 1)
    go = st.button("Run audit", type="primary")

if go:
    try:
        with st.spinner("Auditing…"):
            pages = crawl_start(url, limit=crawl_n)
        st.success(f"Done. Audited {len(pages)} page(s).")

        # Summary of scores
        st.subheader("Scores")
        for p in pages:
            st.metric(p["url"], p["score"])

        # Details per page
        for p in pages:
            with st.expander(f"Details — {p['url']}"):
                st.write("**Breakdown**", {k: round(v) for k,v in p["breakdown"].items()})
                st.write("**Key checks**", {
                    "Skip link": p["checks"]["hasSkipLink"],
                    "Has H1": p["checks"]["hasH1"],
                    "Heading jumps": p["checks"]["headingJumps"],
                    "Landmarks": p["checks"]["landmarkCount"],
                    "Flesch": round(p["checks"]["readingEase"]),
                    "Avg sentence length": round(p["checks"]["avgSentence"],1),
                    "Long paragraphs (120+ words)": p["checks"]["longParagraphs"],
                    "Alt coverage": f"{round(p['checks']['imgAltCoverage']*100)}%",
                    "Unlabeled buttons": p["checks"]["unlabeledButtons"],
                    "Unlabeled inputs": p["checks"]["unlabeledInputs"],
                    "Viewport meta": p["checks"]["viewportMeta"],
                    "Blocks zoom": p["checks"]["viewportBlocksZoom"],
                    "Vague links": f"{p['checks']['vagueLinks']}/{p['checks']['totalLinks']}",
                    "External links without warn": p["checks"]["externalNoWarn"],
                    "Contact discoverability": {"tel": p["checks"]["hasTelLink"], "mailto": p["checks"]["hasMailto"], "contact word": p["checks"]["hasContactWord"]},
                    "Input types": p["checks"]["inputTypes"],
                    "Missing email type": p["checks"]["missingEmailType"],
                    "Missing tel type": p["checks"]["missingTelType"],
                    "Missing autocomplete fields": p["checks"]["missingAutocomplete"],
                    "Captcha text found": p["checks"]["hasCaptchaText"],
                    "Age-gate words": p["checks"]["hasAgeGateWords"],
                })
                if p["recommendations"]:
                    st.write("**PM-ready recommendations**")
                    for r in p["recommendations"]:
                        st.write("• " + r)

        # Exports
        csv_bytes = to_csv(pages)
        pdf_bytes = to_pdf(pages)
        st.download_button("Export CSV tickets", data=csv_bytes, file_name="shuru-tickets.csv", mime="text/csv")
        st.download_button("Download PDF report", data=pdf_bytes, file_name="shuru-report.pdf", mime="application/pdf")

    except Exception as e:
        st.error(str(e))

st.markdown("<hr/>", unsafe_allow_html=True)
st.caption("© 2025 InfraJoy Labs — All rights reserved.")
