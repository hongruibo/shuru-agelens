# Shuru AgeLens — Audit + Agents (Clone & Batch) + Standards
# Dependencies: streamlit, requests, beautifulsoup4
import re, urllib.parse, collections, time
from io import BytesIO
from zipfile import ZipFile

import requests
from bs4 import BeautifulSoup
import streamlit as st
import streamlit.components.v1 as components

# =============== General helpers ===============
UA = "InfraJoy-Shuru-AgeLens/1.0 (+age-inclusion)"
DATA_URI_MAX = 2_000_000  # ~2MB safety cap

def fetch_html(url: str, timeout=20) -> str:
    headers = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"}
    r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text

def domain(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.lower()
    except Exception:
        return ""

def abs_url(base: str, href: str) -> str:
    return urllib.parse.urljoin(base, href)

def textify(node) -> str:
    return re.sub(r"\s+", " ", (node.get_text() if node else "")).strip()

def html_data_uri(html: str) -> str | None:
    try:
        encoded = urllib.parse.quote(html)
        uri = f"data:text/html;charset=utf-8,{encoded}"
        return uri if len(uri) <= DATA_URI_MAX else None
    except Exception:
        return None

def make_zip(files: dict[str, bytes]) -> bytes:
    buf = BytesIO()
    with ZipFile(buf, "w") as z:
        for path, data in files.items():
            z.writestr(path, data)
    return buf.getvalue()

# =============== Readability (Flesch) ===============
def count_syllables(word: str) -> int:
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w: return 0
    w = re.sub(r"e$", "", w)
    groups = re.findall(r"[aeiouy]+", w)
    return max(1, len(groups))

def flesch(text: str) -> float:
    sents = max(1, len(re.findall(r"[.!?]+", text)))
    words = [w for w in re.split(r"\s+", text) if w]
    wc = max(1, len(words))
    syll = sum(count_syllables(w) for w in words)
    wps = wc / sents
    spw = syll / wc
    score = 206.835 - 1.015 * wps - 84.6 * spw
    return max(0, min(120, score))

# =============== Contrast (inline-style heuristic) ===============
def _parse_css_color(s: str):
    if not s: return None
    s = s.strip().lower()
    try:
        if s.startswith("#"):
            v = s[1:]
            if len(v)==3:
                r = int(v[0]*2,16); g = int(v[1]*2,16); b = int(v[2]*2,16)
            elif len(v)==6:
                r = int(v[0:2],16); g = int(v[2:4],16); b = int(v[4:6],16)
            else:
                return None
            return (r/255.0, g/255.0, b/255.0, 1.0)
        if s.startswith("rgb(") or s.startswith("rgba("):
            nums = s[s.find("(")+1:s.find(")")].split(",")
            r = float(nums[0].strip())/255.0
            g = float(nums[1].strip())/255.0
            b = float(nums[2].strip())/255.0
            a = float(nums[3].strip()) if len(nums)>3 else 1.0
            if a>1: a = a/255.0
            return (r,g,b,a)
    except Exception:
        return None
    return None

def _rel_lum(rgb):
    def f(c): return c/12.92 if c<=0.03928 else ((c+0.055)/1.055)**2.4
    r,g,b,_ = rgb
    return 0.2126*f(r)+0.7152*f(g)+0.0722*f(b)

def contrast_ratio(fg, bg):
    L1 = _rel_lum(fg); L2 = _rel_lum(bg)
    hi, lo = max(L1,L2), min(L1,L2)
    return (hi+0.05)/(lo+0.05)

def _style_lookup(el, name: str):
    s = (el.get("style") or "")
    m = re.search(rf"{name}\s*:\s*([^;]+)", s, re.I)
    return (m.group(1).strip() if m else "").strip()

def find_low_contrast_nodes(soup):
    results = []
    for el in soup.select("*"):
        color = _parse_css_color(_style_lookup(el,"color"))
        bg = _parse_css_color(_style_lookup(el,"background-color"))
        if not color or not bg:
            continue
        txt = (el.get_text() or "").strip()
        if not txt: 
            continue
        ratio = contrast_ratio(color, bg)
        fs = _style_lookup(el, "font-size")
        is_large = False
        if fs:
            m = re.match(r"([\d\.]+)\s*px", fs)
            if m:
                px = float(m.group(1))
                is_large = px >= 18.66 or px >= 24
        threshold = 3.0 if is_large else 4.5
        if ratio < threshold:
            results.append({
                "tag": el.name, 
                "text": txt[:120], 
                "ratio": round(ratio,2), 
                "color": _style_lookup(el,"color"), 
                "bg": _style_lookup(el,"background-color")
            })
    return results

# =============== Age-friendly CSS + Transformer ===============
def build_age_friendly_css(
    scale=1.25, underline_links=True, min_targets=True,
    focus_outline=True, reduced_motion=True,
    font_stack="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
) -> str:
    css = [
        f"html {{ font-size: calc(16px * {scale}); }}",
        f"body {{ line-height:1.6; font-family:{font_stack}; max-width:90ch; margin-inline:auto; padding:1rem; }}",
        "p { margin: 0.75em 0; }"
    ]
    if underline_links:
        css += ["a { text-decoration: underline; text-underline-offset: 2px; }",
                "a:visited { opacity: .9; }"]
    if min_targets:
        css += ["button,a,input,select,textarea { min-height:44px; min-width:44px; }",
                "button,input,select,textarea { font-size:1em; }"]
    if focus_outline:
        css += ["*:focus { outline:3px solid #1a73e8 !important; outline-offset:2px; }"]
    if reduced_motion:
        css += ["@media (prefers-reduced-motion: reduce){*{animation:none!important;transition:none!important;scroll-behavior:auto!important;}}"]
    return "\n".join(css)

VAGUE = {"click here","here","read more","learn more","more","this","link"}

def transform_html(html: str, base_url: str, style_css: str | None = None):
    soup = BeautifulSoup(html, "html.parser")
    changes = []
    body = soup.body or soup

    # Skip link + main
    if not soup.select('a[href^="#"][href*="main"], a[href^="#"][href*="content"], a[href*="skip"]'):
        main = soup.select_one("main") or soup.new_tag("main")
        if not main.get("id"): main["id"] = "main"
        if not soup.select_one("main"): body.insert(0, main)
        skip = soup.new_tag("a", href="#"+main["id"])
        skip.string = "Skip to content"
        skip["style"] = "position:absolute;left:-9999px;top:auto;width:1px;height:1px;overflow:hidden;"
        body.insert(0, skip)
        changes.append("Added Skip to content and <main>.")

    # Viewport + zoom
    vp = soup.select_one('meta[name="viewport"]')
    if not vp:
        vp = soup.new_tag("meta", **{"name":"viewport","content":"width=device-width, initial-scale=1"})
        (soup.head or soup).append(vp)
        changes.append("Added viewport meta.")
    else:
        c = vp.get("content","")
        c = re.sub(r"user-scalable\s*=\s*no","user-scalable=yes", c, flags=re.I)
        c = re.sub(r"maximum-scale\s*=\s*1(\.0+)?","maximum-scale=5", c, flags=re.I)
        vp["content"] = c
        changes.append("Enabled pinch-zoom.")

    # Landmarks
    for tag, role in [("header","banner"),("nav","navigation"),("footer","contentinfo")]:
        if not soup.select(f"{tag},[role={role}]"):
            el = soup.new_tag(tag); body.append(el)
            changes.append(f"Inserted <{tag}> landmark.")

    # Buttons/labels
    for el in soup.select("button,[role=button],a[role=button]"):
        if not (textify(el)) and not (el.get("aria-label") or "").strip():
            el["aria-label"] = "Action"
            changes.append("Added aria-label to unlabeled button/control.")

    # Inputs: type + autocomplete
    for el in soup.select("input"):
        name_id = ((el.get("name") or "")+" "+(el.get("id") or "")).lower()
        t = (el.get("type") or "").lower()
        if "email" in name_id and t!="email": el["type"]="email"; changes.append("Input type=email.")
        if ("phone" in name_id or "tel" in name_id) and t!="tel": el["type"]="tel"; changes.append("Input type=tel.")
        if not el.get("autocomplete"):
            if "email" in name_id: el["autocomplete"]="email"
            elif "first" in name_id and "name" in name_id: el["autocomplete"]="given-name"
            elif "last" in name_id and "name" in name_id: el["autocomplete"]="family-name"
            elif "phone" in name_id or "tel" in name_id: el["autocomplete"]="tel"
            if el.get("autocomplete"): changes.append(f"Autocomplete {el['autocomplete']}.")

    # Links: noopener + de-vague
    for a in soup.select("a[href]"):
        href = a.get("href") or ""
        if href.startswith("http") and domain(href)!=domain(base_url):
            rel = set(a.get("rel") or [])
            if "noopener" not in rel:
                rel.add("noopener"); a["rel"]=" ".join(rel); changes.append("rel=noopener on external link.")
        label=(a.get_text() or "").strip().lower()
        if label in VAGUE:
            new_label=a.get("title") or urllib.parse.urlparse(href).path.strip("/").split("/")[-1] or "Learn more"
            a.string=new_label; changes.append(f"Rewrote vague link to '{new_label}'.")

    # Inject CSS
    if style_css:
        style_tag = soup.new_tag("style", id="shuru-age-css")
        style_tag.string = style_css
        (soup.head or soup).insert(0, style_tag)
        changes.append("Injected age-friendly CSS.")

    return str(soup), changes

# =============== Audit (scoring) ===============
def audit_page(url: str) -> dict:
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")

    body_text = textify(soup.body or soup)
    word_count = len(body_text.split())

    # Headings / structure
    headings = soup.select("h1, h2, h3, h4, h5, h6")
    h_levels = [int(h.name[1]) for h in headings]
    has_h1 = bool(soup.select("h1"))
    heading_jumps = sum(1 for i in range(1, len(h_levels)) if h_levels[i] - h_levels[i-1] > 1)

    # Skip & landmarks
    has_skip = any(("#" in (a.get("href") or "")) and (re.search(r"(content|main|skip)", a.get("href") or "", re.I) or re.search(r"skip", textify(a), re.I)) for a in soup.select("a"))
    landmark_count = sum(bool(soup.select(sel)) for sel in ["main,[role=main]","nav,[role=navigation]","header,[role=banner]","footer,[role=contentinfo]"])

    # Readability
    reading_ease = flesch(body_text)

    # Alternatives
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
    input_types = collections.Counter((el.get("type") or "").lower() for el in soup.select("input"))
    missing_email_type = any((el.get("type") or "").lower() != "email" and re.search(r"email", (el.get("name") or "") + (el.get("id") or ""), re.I) for el in soup.select("input"))
    missing_tel_type = any((el.get("type") or "").lower() != "tel" and re.search(r"(phone|tel)", (el.get("name") or "") + (el.get("id") or ""), re.I) for el in soup.select("input"))
    missing_autocomplete = sum(1 for el in soup.select("input,select,textarea") if not (el.get("autocomplete") or "").strip())

    # Viewport & zoom
    viewport_el = soup.select_one('meta[name=viewport]')
    viewport = (viewport_el.get("content") if viewport_el else "") or ""
    viewport_meta = bool(viewport_el)
    viewport_blocks_zoom = bool(re.search(r"user-scalable\s*=\s*no", viewport, re.I) or re.search(r"maximum-scale\s*=\s*1(\.0+)?", viewport, re.I))

    # Links & clarity
    links = soup.select("a[href]")
    total_links, vague_links, external_no_warn = 0, 0, 0
    for a in links:
        total_links += 1
        label = textify(a).lower()
        if label in VAGUE: vague_links += 1
        href = a.get("href") or ""
        if href.startswith("http") and domain(href) and domain(href) != domain(url):
            rel = (a.get("rel") or [])
            if "noopener" not in rel and "noreferrer" not in rel:
                external_no_warn += 1

    # Contact discoverability
    has_tel_link = any(re.match(r"tel:\+?\d", (a.get("href") or ""), re.I) for a in links)
    has_mailto = any((a.get("href") or "").lower().startswith("mailto:") for a in links)
    has_contact_word = re.search(r"\b(contact|support|help|call us|phone)\b", body_text, re.I) is not None

    # Contrast
    low_contrast = find_low_contrast_nodes(soup)

    # ---- Subscores (0..100) ----
    heading_score = (60 if has_h1 else 0) + max(0, 40 - min(4, heading_jumps)*10)
    structure_nav = 0.4*(100 if has_skip else 0) + 0.4*heading_score + 0.2*min(100, (landmark_count/4)*100)
    text_readability = max(0, min(100, reading_ease))
    visual_alternatives = img_alt_coverage*100
    controls_forms = max(0, 100 - (0.6*min(100,unlabeled_buttons*5) + 0.4*min(100,unlabeled_inputs*5)))
    mobile_zoom = 0.6*(100 if viewport_meta else 0) + 0.4*(0 if viewport_blocks_zoom else 100)
    link_clarity = 100 if total_links==0 else max(0, 100 - (vague_links/total_links)*100)
    discoverability = min(100, (35 if has_tel_link else 0) + (25 if has_mailto else 0) + (40 if has_contact_word else 0))

    # Weighted overall (publish these weights)
    score = round(
        0.18*structure_nav +
        0.20*text_readability +
        0.15*visual_alternatives +
        0.20*controls_forms +
        0.12*mobile_zoom +
        0.10*link_clarity +
        0.05*discoverability
    )

    # Recommendations (concise)
    recs = []
    if not has_skip: recs.append("Add a visible 'Skip to content' link (WCAG 2.4.1).")
    if not has_h1: recs.append("Add a single, descriptive H1.")
    if heading_jumps>0: recs.append("Fix heading hierarchy to avoid level jumps.")
    if landmark_count<3: recs.append("Include landmarks: <main>, <nav>, <header>, <footer>.")
    if img_alt_coverage<1: recs.append(f"Add alt text (~{round((1-img_alt_coverage)*100)}% missing) (WCAG 1.1.1).")
    if unlabeled_buttons>0: recs.append(f"Label buttons/controls ({unlabeled_buttons} unlabeled) (WCAG 4.1.2).")
    if unlabeled_inputs>0: recs.append(f"Associate labels with inputs ({unlabeled_inputs} unlabeled) (WCAG 3.3.2).")
    if not viewport_meta: recs.append("Add responsive viewport meta (WCAG 1.4.10).")
    if viewport_blocks_zoom: recs.append("Allow pinch-zoom (remove user-scalable=no / max-scale=1) (WCAG 1.4.4).")
    if text_readability<60: recs.append(f"Simplify copy; Flesch {round(text_readability)} (target 60–70).")
    if vague_links>0: recs.append(f"Replace vague link text ({vague_links}) with descriptive labels (WCAG 2.4.4).")
    if not has_tel_link: recs.append("Expose a tap-to-call link (tel:+…).")
    if not has_mailto: recs.append("Expose a mailto support link or contact form.")
    if missing_email_type: recs.append("Use <input type='email'> for email fields.")
    if missing_tel_type: recs.append("Use <input type='tel'> for phone fields.")
    if missing_autocomplete>0: recs.append("Add autocomplete hints (name, email, address…).")
    if external_no_warn>0: recs.append("Mark external links with rel=noopener / clear labels.")
    if len(low_contrast)>0: recs.append(f"Improve low text/background contrast on {len(low_contrast)} element(s).")

    checks = dict(
        wordCount=word_count, readingEase=reading_ease,
        hasH1=has_h1, headingJumps=heading_jumps,
        hasSkipLink=has_skip, landmarkCount=landmark_count,
        imgAltCoverage=img_alt_coverage, unlabeledButtons=unlabeled_buttons,
        unlabeledInputs=unlabeled_inputs, inputTypes=dict(input_types),
        missingEmailType=missing_email_type, missingTelType=missing_tel_type,
        missingAutocomplete=missing_autocomplete, viewportMeta=viewport_meta,
        viewportBlocksZoom=viewport_blocks_zoom, totalLinks=total_links,
        vagueLinks=vague_links, externalNoWarn=external_no_warn,
        hasTelLink=has_tel_link, hasMailto=has_mailto, hasContactWord=has_contact_word,
        lowContrastCount=len(low_contrast), lowContrastExamples=low_contrast[:10]
    )
    breakdown = dict(
        structureNav=structure_nav, textReadability=text_readability, visualAlternatives=visual_alternatives,
        controlsForms=controls_forms, mobileZoom=mobile_zoom, linkClarity=link_clarity,
        discoverability=discoverability
    )

    return dict(url=url, score=score, breakdown=breakdown, checks=checks, recommendations=recs, html=html)

# =============== Crawler (same-domain) ===============
def crawl_same_domain(start_url: str, limit: int = 5) -> list[str]:
    seen = set([start_url])
    q = collections.deque([start_url])
    host = domain(start_url)
    urls = []
    while q and len(urls) < limit:
        u = q.popleft()
        urls.append(u)
        try:
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
    return urls

# =============== Standards + Explainer ===============
def show_standards():
    st.header("InfraJoy Labs — Age Inclusion Standards (Shuru AgeLens)")
    st.markdown("""
**Backbone:** WCAG 2.2 AA + W3C WAI Older Users + applied research (NN/g, AARP, WHO)

**Pillars**
1) Wayfinding & Structure — skip link, single H1, logical headings, landmarks  
2) Readable Language — aim Flesch 60–70, short sentences, plain language  
3) Visual Alternatives — alt text; captions/transcripts for A/V; reduced motion  
4) Controls & Forms — visible labels; type=email/tel; autocomplete; error prevention  
5) Mobile & Zoom — responsive viewport; never block pinch-zoom  
6) Link Clarity — descriptive anchors; avoid “click here”; rel=noopener for external links  
7) Discoverability & Low Friction — obvious contact paths; avoid hostile CAPTCHAs/age-gates
""")

    st.subheader("Scoring Weights")
    st.write({
        "Structure & Nav": "18%",
        "Text Readability": "20%",
        "Visual Alternatives": "15%",
        "Controls & Forms": "20%",
        "Mobile & Zoom": "12%",
        "Link Clarity": "10%",
        "Contact Discoverability": "5% (advisory)"
    })

    st.subheader("Founder’s Note")
    st.markdown("""
**InfraJoy Labs** was founded by **Linda Hong Cheng** (Clarendon Scholar, Oxford), whose work spans
**digital inclusion**, **age-friendly design**, and **algorithmic equity**. Shuru AgeLens turns those
principles into actionable audits and one-click remediations.
""")

def show_audit_explainer():
    st.subheader("📊 What does the Audit Score mean?")
    st.markdown("""
The **Audit Score (0–100)** reflects how well a page aligns with age-inclusive best practices derived
from **WCAG 2.2**, **WAI Older Users guidance**, and applied usability research for older adults.
**100** ≈ strong alignment; **50–70** = partial; **<50** = major barriers.
""")

# =============== Streamlit UI ===============
st.set_page_config(page_title="Shuru AgeLens", layout="wide")
st.title("Shuru AgeLens — Age-Inclusive Web Audit & Agents")

page = st.sidebar.radio("Navigate", ["Audit", "Agents (Clone)", "Agents (Batch Clone)", "Standards / About"], index=0)

# ---- Agents (Clone) ----
if page == "Agents (Clone)":
    st.header("Age-Friendly Clone (single page)")
    url_clone = st.text_input("URL to clone", "https://example.com")
    col1, col2 = st.columns(2)
    with col1:
        scale = st.slider("Text scale", 1.0, 1.6, 1.25, 0.05)
        underline = st.checkbox("Underline links", True)
        targets = st.checkbox("Minimum touch targets (44×44)", True)
    with col2:
        focus = st.checkbox("Strong focus outline", True)
        reduced = st.checkbox("Respect reduced motion", True)
        fontstack = st.text_input("Font stack", "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif")

    if st.button("Generate age-friendly clone", type="primary"):
        try:
            html_orig = fetch_html(url_clone)
            css = build_age_friendly_css(scale, underline, targets, focus, reduced, fontstack)
            html_fixed, changes = transform_html(html_orig, url_clone, style_css=css)
            files = {
                "index_age_friendly.html": html_fixed.encode("utf-8"),
                "SHURU_CHANGELOG.txt": ("\n".join(changes) or "No changes").encode("utf-8"),
            }
            st.success("Clone generated.")
            st.download_button("⬇️ Download age-friendly copy (ZIP)", data=make_zip(files),
                               file_name="shuru_age_friendly.zip", mime="application/zip")

            st.subheader("Preview (age-friendly)")
            components.html(html_fixed, height=800, scrolling=True)

            data_uri = html_data_uri(html_fixed)
            if data_uri:
                st.markdown(f'<p><a href="{data_uri}" target="_blank" rel="noopener">🔗 Open clone in a new tab</a></p>', unsafe_allow_html=True)
            else:
                st.info("Page too large for a data link — use the ZIP download.")

            with st.expander("What changed"):
                for c in changes: st.write("• " + c)
        except Exception as e:
            st.error(str(e))

# ---- Agents (Batch Clone) ----
elif page == "Agents (Batch Clone)":
    st.header("Batch Clone: crawl, fix, and package multiple pages")
    root = st.text_input("Start URL (same-domain crawl)", "https://example.com")
    n = st.slider("Max pages to clone", 1, 15, 5)
    scale = st.slider("Text scale", 1.0, 1.6, 1.25, 0.05)

    if st.button("Run batch clone", type="primary"):
        try:
            urls = crawl_same_domain(root, n)
            fixed_map = []
            zfiles = {}
            css = build_age_friendly_css(scale=scale)

            for i, u in enumerate(urls, start=1):
                try:
                    html = fetch_html(u)
                    fixed, changes = transform_html(html, u, style_css=css)
                    fname = f"page_{i}.html"
                    fixed_map.append((u, fname, changes))
                    zfiles[fname] = fixed.encode("utf-8")
                    zfiles[f"changelogs/{fname}.txt"] = ("\n".join(changes) or "No changes").encode("utf-8")
                except Exception as e:
                    zfiles[f"errors/page_{i}.txt"] = (str(e)).encode("utf-8")

            # Build index.html with links
            links_html = "\n".join([f'<li><a href="{fname}">{urllib.parse.quote(u, safe=":/?#[]@!$&\'()*+,;=")}</a></li>' for (u, fname, _) in fixed_map])
            index_html = f"""<!doctype html><html><head><meta charset="utf-8"><title>Shuru Batch Clone</title></head>
<body><h1>Shuru Age-Friendly Batch Clone</h1><ul>{links_html}</ul></body></html>"""
            zfiles["index.html"] = index_html.encode("utf-8")

            # Primary download
            batch_zip = make_zip(zfiles)
            st.download_button("⬇️ Download batch ZIP", data=batch_zip, file_name="shuru_batch_clone.zip", mime="application/zip")

            if fixed_map:
                # Preview first fixed page + data link
                first_url, first_file, _ = fixed_map[0]
                st.subheader("Preview (first page)")
                first_fixed_html = zfiles[first_file].decode("utf-8", errors="ignore")
                components.html(first_fixed_html, height=800, scrolling=True)
                data_uri = html_data_uri(first_fixed_html)
                if data_uri:
                    st.markdown(f'<p><a href="{data_uri}" target="_blank" rel="noopener">🔗 Open first clone in a new tab</a></p>', unsafe_allow_html=True)
            st.success(f"Cloned {len(fixed_map)} page(s).")

        except Exception as e:
            st.error(str(e))

# ---- Standards / About ----
elif page == "Standards / About":
    show_standards()

# ---- Audit ----
else:
    st.header("Audit a website")
    url = st.text_input("URL", "https://example.com")
    pages = st.slider("Pages to audit (same-domain crawl)", 1, 10, 1)

    if st.button("Run audit", type="primary"):
        try:
            urls = crawl_same_domain(url, pages)
            results = []
            for u in urls:
                try:
                    results.append(audit_page(u))
                except Exception:
                    continue

            if not results:
                st.warning("No pages audited. Check the URL and try again.")
            else:
                # Show scores + breakdown
                st.subheader("Scores")
                for r in results:
                    st.metric(r["url"], r["score"])

                for r in results:
                    with st.expander(f"Details — {r['url']} (Score {r['score']})"):
                        st.write("**Breakdown**", {k: round(v) for k,v in r["breakdown"].items()})
                        st.write("**Checks**", {
                            "Skip link": r["checks"]["hasSkipLink"],
                            "Has H1": r["checks"]["hasH1"],
                            "Heading jumps": r["checks"]["headingJumps"],
                            "Landmarks": r["checks"]["landmarkCount"],
                            "Flesch": round(r["checks"]["readingEase"]),
                            "Alt coverage": f"{round(r['checks']['imgAltCoverage']*100)}%",
                            "Unlabeled buttons": r["checks"]["unlabeledButtons"],
                            "Unlabeled inputs": r["checks"]["unlabeledInputs"],
                            "Viewport meta": r["checks"]["viewportMeta"],
                            "Blocks zoom": r["checks"]["viewportBlocksZoom"],
                            "Vague links": f"{r['checks']['vagueLinks']}/{r['checks']['totalLinks']}",
                            "External links w/o warn": r["checks"]["externalNoWarn"],
                            "Contact discoverability": {"tel": r["checks"]["hasTelLink"], "mailto": r["checks"]["hasMailto"], "keyword": r["checks"]["hasContactWord"]},
                            "Low-contrast elements (inline)": r["checks"]["lowContrastCount"],
                        })
                        if r["recommendations"]:
                            st.write("**Recommendations**")
                            for rec in r["recommendations"]:
                                st.write("• " + rec)

                # One-click clone for first audited page
                first = results[0]
                css = build_age_friendly_css()
                fixed_html, changes = transform_html(first["html"], first["url"], style_css=css)
                files = {
                    "index_age_friendly.html": fixed_html.encode("utf-8"),
                    "SHURU_CHANGELOG.txt": ("\n".join(changes) or "No changes").encode("utf-8"),
                }
                st.subheader("Age-Friendly Copy (first page)")
                st.download_button("⬇️ Download age-friendly copy (ZIP)", data=make_zip(files),
                                   file_name="shuru_age_friendly.zip", mime="application/zip")

                st.subheader("Preview (age-friendly)")
                components.html(fixed_html, height=800, scrolling=True)
                data_uri = html_data_uri(fixed_html)
                if data_uri:
                    st.markdown(f'<p><a href="{data_uri}" target="_blank" rel="noopener">🔗 Open clone in a new tab</a></p>', unsafe_allow_html=True)

                show_audit_explainer()

        except Exception as e:
            st.error(str(e))

st.markdown("<hr/>", unsafe_allow_html=True)
st.caption("© 2025 InfraJoy Labs — All rights reserved.")

