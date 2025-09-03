import re, json, urllib.parse, requests
from collections import Counter, deque
from io import BytesIO
from zipfile import ZipFile
from bs4 import BeautifulSoup
import streamlit as st
from fpdf import FPDF

UA = "InfraJoy-Shuru-AgeLens/1.0 (Python)"

# ---------- Utilities ----------
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

# ---------- Audit a single page ----------
def audit_page(url: str) -> dict:
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")

    body_text = textify(soup.body or soup)
    word_count = len(body_text.split())

    # Headings & structure
    headings = soup.select("h1, h2, h3, h4, h5, h6")
    h_levels = [int(h.name[1]) for h in headings]
    has_h1 = bool(soup.select("h1"))
    heading_jumps = sum(1 for i in range(1, len(h_levels)) if h_levels[i] - h_levels[i-1] > 1)

    # Skip link & landmarks
    has_skip = any(
        ("#" in (a.get("href") or "")) and
        (re.search(r"(content|main|skip)", a.get("href") or "", re.I) or re.search(r"skip", textify(a), re.I))
        for a in soup.select("a")
    )
    landmark_count = sum(bool(soup.select(sel)) for sel in [
        "main,[role=main]","nav,[role=navigation]","header,[role=banner]","footer,[role=contentinfo]",
    ])

    # Readability
    reading_ease = flesch(body_text)
    sentence_count = max(1, len(re.findall(r"[.!?]+", body_text)))
    avg_sentence_len = word_count / sentence_count
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

    # Input hygiene
    input_types = Counter((el.get("type") or "").lower() for el in soup.select("input"))
    missing_email_type = any((el.get("type") or "").lower() != "email" and re.search(r"email", (el.get("name") or "") + (el.get("id") or ""), re.I) for el in soup.select("input"))
    missing_tel_type = any((el.get("type") or "").lower() != "tel" and re.search(r"(phone|tel)", (el.get("name") or "") + (el.get("id") or ""), re.I) for el in soup.select("input"))
    missing_autocomplete = sum(1 for el in soup.select("input,select,textarea") if not (el.get("autocomplete") or "").strip())

    # Viewport & zoom
    viewport_el = soup.select_one('meta[name=viewport]')
    viewport = (viewport_el.get("content") if viewport_el else "") or ""
    viewport_meta = bool(viewport_el)
    viewport_blocks_zoom = bool(re.search(r"user-scalable\s*=\s*no", viewport, re.I) or re.search(r"maximum-scale\s*=\s*1(\.0+)?", viewport, re.I))

    # Links & clarity
    vague_set = {"click here","here","read more","learn more","more","this","link"}
    links = soup.select("a[href]")
    total_links, vague_links, external_no_warn = 0, 0, 0
    for a in links:
        total_links += 1
        label = textify(a).lower()
        if label in vague_set: vague_links += 1
        href = a.get("href") or ""
        if href.startswith("http") and domain(href) and domain(href) != domain(url):
            rel = (a.get("rel") or [])
            if "noopener" not in rel and "noreferrer" not in rel:
                external_no_warn += 1

    # Contact discoverability
    has_tel_link = any(re.match(r"tel:\+?\d", (a.get("href") or ""), re.I) for a in links)
    has_mailto = any((a.get("href") or "").lower().startswith("mailto:") for a in links)
    has_contact_word = re.search(r"\b(contact|support|help|call us|phone)\b", body_text, re.I) is not None

    # Friction signals
    has_captcha_text = re.search(r"captcha|i am not a robot", body_text, re.I) is not None
    has_age_gate_words = re.search(r"\b(enter your age|over 18|date of birth)\b", body_text, re.I) is not None

    # Subscores 0..100
    heading_score = (60 if has_h1 else 0) + max(0, 40 - min(4, heading_jumps)*10)
    structure_nav = 0.4*(100 if has_skip else 0) + 0.4*heading_score + 0.2*min(100, (landmark_count/4)*100)
    text_readability = max(0, min(100, reading_ease))
    visual_alternatives = img_alt_coverage*100
    controls_forms = max(0, 100 - (0.6*min(100,unlabeled_buttons*5) + 0.4*min(100,unlabeled_inputs*5)))
    mobile_zoom = 0.6*(100 if viewport_meta else 0) + 0.4*(0 if viewport_blocks_zoom else 100)
    link_clarity = 100 if total_links==0 else max(0, 100 - (vague_links/total_links)*100)

    # Advisory extras
    discoverability = min(100, (35 if has_tel_link else 0) + (25 if has_mailto else 0) + (40 if has_contact_word else 0))
    hygiene = max(0, 100 - (15 if missing_email_type else 0) - (15 if missing_tel_type else 0) - min(40, missing_autocomplete*2))
    annoyance = max(0, 100 - (20 if has_captcha_text else 0) - (10 if has_age_gate_words else 0))

    # Overall Shuru score
    score = round(
        0.18*structure_nav + 0.20*text_readability + 0.15*visual_alternatives +
        0.20*controls_forms + 0.12*mobile_zoom + 0.10*link_clarity + 0.05*discoverability
    )

    checks = dict(
        wordCount=word_count, readingEase=reading_ease, avgSentence=avg_sentence_len, longParagraphs=long_paras,
        hasH1=has_h1, headingJumps=heading_jumps, hasSkipLink=has_skip, landmarkCount=landmark_count,
        imgAltCoverage=img_alt_coverage, unlabeledButtons=unlabeled_buttons, unlabeledInputs=unlabeled_inputs,
        inputTypes=dict(input_types), missingEmailType=missing_email_type, missingTelType=missing_tel_type,
        missingAutocomplete=missing_autocomplete, viewportMeta=viewport_meta, viewportBlocksZoom=viewport_blocks_zoom,
        totalLinks=total_links, vagueLinks=vague_links, externalNoWarn=external_no_warn,
        hasTelLink=has_tel_link, hasMailto=has_mailto, hasContactWord=has_contact_word,
        hasCaptchaText=has_captcha_text, hasAgeGateWords=has_age_gate_words,
    )
    breakdown = dict(
        structureNav=structure_nav, textReadability=text_readability, visualAlternatives=visual_alternatives,
        controlsForms=controls_forms, mobileZoom=mobile_zoom, linkClarity=link_clarity,
        discoverability=discoverability, hygiene=hygiene, annoyance=annoyance
    )

    # Recommendations
    recs = []
    if not has_skip: recs.append("Add a visible 'Skip to content' link (WCAG 2.4.1).")
    if not has_h1: recs.append("Add a single, descriptive H1.")
    if heading_jumps>0: recs.append(f"Fix heading hierarchy (avoid jumps; {heading_jumps}).")
    if landmark_count<3: recs.append("Include landmarks: <main>, <nav>, <header>, <footer>.")
    if img_alt_coverage<1: recs.append(f"Add alt text (~{round((1-img_alt_coverage)*100)}% missing) (WCAG 1.1.1).")
    if unlabeled_buttons>0: recs.append(f"Label buttons/controls ({unlabeled_buttons} unlabeled) (WCAG 4.1.2).")
    if unlabeled_inputs>0: recs.append(f"Associate labels with inputs ({unlabeled_inputs} unlabeled) (WCAG 3.3.2).")
    if not viewport_meta: recs.append("Add responsive viewport meta (WCAG 1.4.10).")
    if viewport_blocks_zoom: recs.append("Allow pinch-zoom (remove user-scalable=no / maximum-scale=1) (WCAG 1.4.4).")
    if text_readability<60: recs.append(f"Simplify copy; Flesch {round(text_readability)} (target 60–70).")
    if vague_links>0: recs.append(f"Replace vague link text ({vague_links}) with descriptive labels (WCAG 2.4.4).")
    if not has_tel_link: recs.append("Expose a tap-to-call link (tel:+…).")
    if not has_mailto: recs.append("Expose a mailto: support link or contact form.")
    if missing_email_type: recs.append("Use <input type='email'> for email fields (mobile keyboard).")
    if missing_tel_type: recs.append("Use <input type='tel'> for phone fields (dial pad).")
    if missing_autocomplete>0: recs.append("Add autocomplete hints (name, email, address, etc.).")
    if external_no_warn>0: recs.append("Mark external links with rel=noopener and/or clear labels.")
    if has_captcha_text: recs.append("Offer accessible alternatives to CAPTCHAs.")
    if has_age_gate_words: recs.append("Age-gates: use plain language and accessible date inputs.")

    return dict(url=url, score=score, checks=checks, breakdown=breakdown, recommendations=recs)

# ---------- Mini crawler ----------
def crawl_start(url: str, limit: int = 1):
    seen = set([url])
    q = deque([url])
    host = domain(url)
    pages = []
    while q and len(pages) < limit:
        u = q.popleft()
        try:
            res = audit_page(u)
            pages.append(res)
            html = fetch_html(u)
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.select("a[href]"):
                href = a.get("href") or ""
                if href.startswith("#"): continue
                v = abs_url(u, href)
                if domain(v) == host and v not in seen:
                    seen.add(v); q.append(v)
        except Exception:
            continue
    return pages

# ---------- Age-friendly transformer ----------
VAGUE = {"click here","here","read more","learn more","more","this","link"}

def transform_html(html: str, base_url: str):
    soup = BeautifulSoup(html, "html.parser")
    changes = []
    body = soup.body or soup

    # Skip link + main
    if not soup.select('a[href^="#"][href*="main"], a[href^="#"][href*="content"], a[href*="skip"]'):
        main = soup.select_one("main")
        if not main:
            main = soup.new_tag("main"); body.insert(0, main)
        if not main.get("id"): main["id"] = "main"
        skip = soup.new_tag("a", href="#"+main["id"])
        skip.string = "Skip to content"
        skip["style"] = "position:absolute;left:-9999px;top:auto;width:1px;height:1px;overflow:hidden;"
        body.insert(0, skip)
        changes.append("Added Skip to content and ensured <main> exists.")

    # Viewport + zoom
    vp = soup.select_one('meta[name="viewport"]')
    if not vp:
        vp = soup.new_tag("meta", **{"name":"viewport","content":"width=device-width, initial-scale=1"})
        (soup.head or soup).append(vp)
        changes.append("Added responsive viewport meta.")
    else:
        c = vp.get("content","")
        c = re.sub(r"user-scalable\s*=\s*no","user-scalable=yes", c, flags=re.I)
        c = re.sub(r"maximum-scale\s*=\s*1(\.0+)?","maximum-scale=5", c, flags=re.I)
        vp["content"] = c
        changes.append("Unblocked pinch-zoom in viewport.")

    # Landmarks
    if not soup.select("header,[role=banner]"):
        hdr = soup.new_tag("header"); body.insert(0, hdr)
        changes.append("Inserted <header> landmark placeholder.")
    if not soup.select("nav,[role=navigation]"):
        nav = soup.new_tag("nav"); body.insert(1, nav)
        changes.append("Inserted <nav> landmark placeholder.")
    if not soup.select("footer,[role=contentinfo]"):
        f = soup.new_tag("footer"); body.append(f)
        changes.append("Inserted <footer> landmark placeholder.")

    # Buttons/interactive labels
    for el in soup.select("button, [role=button], a[role=button]"):
        if not (el.get_text() or "").strip() and not (el.get("aria-label") or "").strip():
            el["aria-label"] = "Action"
            changes.append("Added aria-label to unlabeled button/control.")

    # Inputs: type + autocomplete
    for el in soup.select("input"):
        name_id = ((el.get("name") or "") + " " + (el.get("id") or "")).lower()
        t = (el.get("type") or "").lower()
        if "email" in name_id and t != "email":
            el["type"] = "email"; changes.append("Set input type=email.")
        if ("phone" in name_id or "tel" in name_id) and t != "tel":
            el["type"] = "tel"; changes.append("Set input type=tel.")
        if not el.get("autocomplete"):
            if "email" in name_id: el["autocomplete"] = "email"
            elif "first" in name_id and "name" in name_id: el["autocomplete"] = "given-name"
            elif "last" in name_id and "name" in name_id: el["autocomplete"] = "family-name"
            elif "phone" in name_id or "tel" in name_id: el["autocomplete"] = "tel"
            elif "address" in name_id: el["autocomplete"] = "street-address"
            elif "zip" in name_id or "postal" in name_id: el["autocomplete"] = "postal-code"
            elif "city" in name_id: el["autocomplete"] = "address-level2"
            elif "state" in name_id or "province" in name_id: el["autocomplete"] = "address-level1"
            if el.get("autocomplete"):
                changes.append(f"Added autocomplete={el['autocomplete']}.")

    # Links: rel noopener & de-vague labels
    for a in soup.select("a[href]"):
        href = a.get("href") or ""
        if href.startswith("http") and domain(href) != domain(base_url):
            rel = set(a.get("rel") or [])
            if "noopener" not in rel:
                rel.add("noopener"); a["rel"] = " ".join(rel)
                changes.append("Added rel=noopener to external link.")
        label = (a.get_text() or "").strip().lower()
        if label in VAGUE:
            new_label = a.get("title") or urllib.parse.urlparse(href).path.strip("/").split("/")[-1] or "Learn more"
            a.string = new_label
            changes.append(f"Rewrote vague link text to '{new_label}'.")

    return str(soup), changes

def make_zip(filename_html: str, html: str, changes: list[str]) -> bytes:
    buf = BytesIO()
    with ZipFile(buf, "w") as z:
        z.writestr(filename_html, html.encode("utf-8"))
        z.writestr("SHURU_CHANGELOG.txt", ("\n".join(changes) or "No changes").encode("utf-8"))
    return buf.getvalue()

# ---------- Exports ----------
def to_csv(pages: list[dict]) -> bytes:
    rows = ["URL,Priority,Recommendation,Acceptance Criteria"]
    for p in pages:
        for r in p["recommendations"]:
            prio = "High" if any(k in r.lower() for k in ["zoom","captcha","label","viewport"]) else "Medium"
            ac = "Re-run Shuru; rule no longer triggers and page passes associated check."
            def esc(s): return '"' + s.replace('"','""') + '"'
            rows.append(",".join([esc(p["url"]), esc(prio), esc(r), esc(ac)]))
    return ("\n".join(rows)).encode("utf-8")

def to_pdf(pages: list[dict]) -> bytes:
    pdf = FPDF()
    for idx, p in enumerate(pages, start=1):
        pdf.add_page()
        pdf.set_font("Helvetica","",16)
        title = "InfraJoy Labs: Shuru AgeLens — Audit Report"
        if len(pages) > 1: title += f" (page {idx})"
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

# ---------- Standards/About ----------
def show_standards():
    st.header("InfraJoy Labs — Age Inclusion Standards (Shuru AgeLens)")
    st.write("""
**WCAG 2.2/2.1 AA** aligned + **age-friendly** heuristics:
- **Wayfinding & Structure** — skip link (2.4.1), single H1 + logical headings, landmarks.
- **Readable Language** — target **Flesch 60–70**, short sentences, avoid jargon.
- **Visual Alternatives** — descriptive `alt` (1.1.1).
- **Controls & Forms** — labels (3.3.2, 4.1.2), `type=email|tel`, `autocomplete`.
- **Mobile & Zoom** — responsive viewport (1.4.10); **don’t block zoom** (1.4.4).
- **Link Clarity** — avoid “click here” (2.4.4).
- **Discoverability** — clear contact (tel/mailto/keywords).
- **Low Friction** — avoid CAPTCHA/age-gate traps or provide accessible alternatives.
    """)
    st.subheader("Scoring Weights (0–100)")
    st.write({
        "Structure & Nav": "18%",
        "Text Readability": "20%",
        "Visual Alternatives": "15%",
        "Controls & Forms": "20%",
        "Mobile & Zoom": "12%",
        "Link Clarity": "10%",
        "Contact Discoverability": "5% (advisory)",
    })
    st.subheader("Acceptance Criteria Template")
    st.code("Rule no longer triggers on affected elements. Re-audit passes associated checks.", language="text")
    st.subheader("Caveats")
    st.markdown("""Static HTML checks. Dynamic behavior (contrast, focus order, timing, errors) needs manual/headless testing. Do not claim legal compliance solely from this tool.""")

# ---------- UI ----------
st.set_page_config(page_title="InfraJoy Labs: Shuru AgeLens", page_icon="🧭", layout="centered")
st.title("InfraJoy Labs: Shuru AgeLens")

page = st.sidebar.radio("Navigate", ["Audit", "Standards / About"], index=0)

if page == "Standards / About":
    show_standards()
else:
    st.write("Paste a URL to run an **age-inclusive UX** audit. Optionally crawl a few same-domain pages.")
    colA, colB = st.columns([3,1], vertical_alignment="bottom")
    with colA:
        url = st.text_input("URL to audit", value="https://example.com")
    with colB:
        crawl_n = st.slider("Pages", 1, 5, 1)

    if st.button("Run audit", type="primary"):
        try:
            with st.spinner("Auditing…"):
                pages = crawl_start(url, limit=crawl_n)
            st.success(f"Done. Audited {len(pages)} page(s).")

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
                        "Avg sentence": round(p["checks"]["avgSentence"],1),
                        "Long paragraphs (120+ words)": p["checks"]["longParagraphs"],
                        "Alt coverage": f"{round(p['checks']['imgAltCoverage']*100)}%",
                        "Unlabeled buttons": p["checks"]["unlabeledButtons"],
                        "Unlabeled inputs": p["checks"]["unlabeledInputs"],
                        "Viewport meta": p["checks"]["viewportMeta"],
                        "Blocks zoom": p["checks"]["viewportBlocksZoom"],
                        "Vague links": f"{p['checks']['vagueLinks']}/{p['checks']['totalLinks']}",
                        "External links w/o warn": p["checks"]["externalNoWarn"],
                        "Contact discoverability": {"tel": p["checks"]["hasTelLink"], "mailto": p["checks"]["hasMailto"], "keyword": p["checks"]["hasContactWord"]},
                        "Input types": p["checks"]["inputTypes"],
                        "Missing email type": p["checks"]["missingEmailType"],
                        "Missing tel type": p["checks"]["missingTelType"],
                        "Missing autocomplete": p["checks"]["missingAutocomplete"],
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

            # Age-friendly copy (ZIP) for the first page
            if pages:
                try:
                    original_html = fetch_html(pages[0]["url"])
                    fixed_html, changes = transform_html(original_html, pages[0]["url"])
                    zip_bytes = make_zip("index_age_friendly.html", fixed_html, changes)
                    st.subheader("Age-Friendly Copy")
                    st.download_button("⬇️ Download age-friendly copy (ZIP)",
                                       data=zip_bytes,
                                       file_name="shuru_age_friendly.zip",
                                       mime="application/zip")
                    with st.expander("See what we changed"):
                        for c in changes: st.write("• " + c)
                except Exception as e:
                    st.error("Failed to generate age-friendly copy: " + str(e))

        except Exception as e:
            st.error(str(e))

st.markdown("<hr/>", unsafe_allow_html=True)
st.caption("© 2025 InfraJoy Labs — All rights reserved.")
