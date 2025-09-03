def show_standards():
    st.header("InfraJoy Labs — Age Inclusion Standards (Shuru AgeLens)")

    st.markdown("""
Shuru AgeLens blends **WCAG 2.2 AA** with **age-inclusive UX** research to produce a practical,
auditable standard for older adults. Key pillars (v0.1):

### 1) Wayfinding & Page Structure
- Visible **Skip to content** (WCAG 2.4.1)
- Single, descriptive **H1**; logical H2–H6 hierarchy
- Landmarks: `<main>`, `<nav>`, `<header>`, `<footer>`
- Clear link purpose; avoid *“click here”* (WCAG 2.4.4)

**Why it matters:** Older users benefit from consistent structure, larger targets, and reduced cognitive load.  
See W3C WAI on **older users** and how WCAG maps to age needs.  
""")
    st.caption("Refs: W3C WAI Older Users overview; WCAG 2.2 & 'What’s New in 2.2'.")
    st.markdown("""
### 2) Readable Language
- Aim **Flesch 60–70**; short sentences
- Avoid jargon & nested clauses
- Break long paragraphs; use bullets and meaningful headings

**Why it matters:** Reading ease, memory, and scanning speed often change with age; plain language increases task success.  
""")

    st.markdown("""
### 3) Visual Alternatives & Media
- Descriptive **alt** for meaningful images (WCAG 1.1.1)
- Captions/transcripts for A/V (WCAG 1.2.x)
- Respect **prefers-reduced-motion**

### 4) Controls & Forms
- Visible labels (WCAG 3.3.2, 4.1.2)
- Semantic inputs: `type=email`, `type=tel`; `autocomplete` hints
- Error prevention: clear hints & inline errors

### 5) Mobile & Zoom
- Responsive viewport (WCAG 1.4.10)
- **Never block pinch-zoom** (WCAG 1.4.4)

### 6) Link & Action Clarity
- Descriptive link text; avoid vague anchors
- Mark external links with `rel=noopener`

### 7) Discoverability & Low Friction
- Obvious contact paths (tap-to-call/mailto/keywords)
- Avoid hostile CAPTCHAs/age-gates; provide accessible paths
""")

    st.subheader("Evidence & Further Reading")
    st.markdown(
        "- W3C WAI — **Older Users & Web Accessibility** (how WCAG maps to age needs). "
        "[Link](https://www.w3.org/WAI/older-users/)\n"
        "- W3C — **WCAG 2.2** specification + changes from 2.1. "
        "[WCAG 2.2](https://www.w3.org/TR/WCAG22/), "
        "[What’s new](https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/)\n"
        "- Nielsen Norman Group — **Usability for Older Adults** research. "
        "[Guidelines](https://www.nngroup.com/articles/usability-for-senior-citizens/), "
        "[Testing older adults](https://www.nngroup.com/articles/usability-testing-older-adults/)\n"
        "- AARP — **Tech adoption & needs of 50+** (recent trends). "
        "[Overview](https://www.aarp.org/pri/topics/technology/internet-media-devices/2025-technology-trends-older-adults/)\n"
        "- WHO Age-Friendly World — **Communication & Information**. "
        "[Link](https://extranet.who.int/agefriendlyworld/age-friendly-practices/communication-and-information/)"
    )

    st.subheader("Scoring (0–100)")
    st.write({
        "Structure & Nav": "18%",
        "Text Readability": "20%",
        "Visual Alternatives": "15%",
        "Controls & Forms": "20%",
        "Mobile & Zoom": "12%",
        "Link Clarity": "10%",
        "Contact Discoverability": "5% (advisory)"
    })

    st.subheader("Acceptance Criteria Template")
    st.code("Rule no longer triggers on affected elements. Re-audit passes associated checks.", language="text")

    st.subheader("Caveats")
    st.markdown("""
This prototype inspects **static HTML**. Dynamic behaviours (contrast, focus order,
timings, error states/ARIA) need manual or headless checks. Don’t claim legal compliance
solely from this tool; use it as triage to drive remediation.
""")
# All your Python or HTML or CSS code goes here
# Even things like !important will be safe
print("Hello, world!  font-size: 24px !important;")


# Shuru AgeLens MVP with Audit, Agents (Clone), and Standards/About pages
import re, urllib.parse, csv, io
import requests
from bs4 import BeautifulSoup
import streamlit as st
from fpdf import FPDF
from zipfile import ZipFile
from io import BytesIO

# ------------------------------
# Helper functions
# ------------------------------
def fetch_html(url: str) -> str:
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    return r.text

def domain(u): 
    try: return urllib.parse.urlparse(u).netloc.lower()
    except: return ""

def make_zip(filename_html: str, html: str, changes: list[str]) -> bytes:
    buf = BytesIO()
    with ZipFile(buf, "w") as z:
        z.writestr(filename_html, html.encode("utf-8"))
        z.writestr("SHURU_CHANGELOG.txt", ("\n".join(changes) or "No changes").encode("utf-8"))
    return buf.getvalue()

def build_age_friendly_css(
    scale=1.25,
    underline_links=True,
    min_targets=True,
    focus_outline=True,
    reduced_motion=True,
    font_stack="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
) -> str:
    css = [
        "html { font-size: calc(16px * %.2f); }" % scale,
        "body { line-height:1.6; font-family:%s; max-width:90ch; margin-inline:auto; padding:1rem; }" % font_stack,
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
        if not (el.get_text() or "").strip() and not el.get("aria-label"):
            el["aria-label"] = "Action"
            changes.append("Added aria-label to unlabeled button.")

    # Inputs: type + autocomplete
    for el in soup.select("input"):
        name_id = ((el.get("name") or "")+" "+(el.get("id") or "")).lower()
        t = (el.get("type") or "").lower()
        if "email" in name_id and t!="email": el["type"]="email"; changes.append("Input type=email")
        if ("phone" in name_id or "tel" in name_id) and t!="tel": el["type"]="tel"; changes.append("Input type=tel")
        if not el.get("autocomplete"):
            if "email" in name_id: el["autocomplete"]="email"
            elif "first" in name_id and "name" in name_id: el["autocomplete"]="given-name"
            elif "last" in name_id and "name" in name_id: el["autocomplete"]="family-name"
            elif "phone" in name_id or "tel" in name_id: el["autocomplete"]="tel"
            if el.get("autocomplete"): changes.append(f"Autocomplete {el['autocomplete']}")

    # Links: noopener + vague
    VAGUE = {"click here","here","read more","learn more","more","this","link"}
    for a in soup.select("a[href]"):
        href = a.get("href") or ""
        if href.startswith("http") and domain(href)!=domain(base_url):
            rel = set(a.get("rel") or [])
            if "noopener" not in rel:
                rel.add("noopener"); a["rel"]=" ".join(rel); changes.append("rel=noopener on external link")
        label=(a.get_text() or "").strip().lower()
        if label in VAGUE:
            new_label=a.get("title") or urllib.parse.urlparse(href).path.strip("/").split("/")[-1] or "Learn more"
            a.string=new_label; changes.append(f"Rewrote vague link to '{new_label}'")

    if style_css:
        style_tag = soup.new_tag("style", id="shuru-age-css")
        style_tag.string = style_css
        (soup.head or soup).insert(0, style_tag)
        changes.append("Injected age-friendly CSS.")

    return str(soup), changes

# ------------------------------
# Streamlit UI
# ------------------------------
st.set_page_config(page_title="Shuru AgeLens", layout="wide")
st.title("Shuru AgeLens — Age-Inclusive Web Audit & Agents")

page = st.sidebar.radio("Navigate", ["Audit","Agents (Clone)","Standards / About"], index=0)

# --- Standards/About page
def show_standards():
    st.header("InfraJoy Labs — Age Inclusion Standards")
    st.markdown("""
### Key Pillars
1. **Wayfinding & Structure:** Skip link, H1 hierarchy, landmarks
2. **Readable Language:** Plain language, Flesch 60–70, short sentences
3. **Visual Alternatives:** Alt text, captions, reduced motion
4. **Controls & Forms:** Labels, type=email/tel, autocomplete
5. **Mobile & Zoom:** Responsive viewport, never block pinch-zoom
6. **Links & Actions:** Descriptive anchors, rel=noopener for externals
7. **Discoverability:** Contact info, avoid hostile captchas
    """)
    st.subheader("Evidence")
    st.markdown("""
- [W3C WAI Older Users](https://www.w3.org/WAI/older-users/)
- [WCAG 2.2](https://www.w3.org/TR/WCAG22/) & [What's new in 2.2](https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/)
- [NN/g Usability for Seniors](https://www.nngroup.com/articles/usability-for-senior-citizens/)
- [AARP Tech Adoption 50+](https://www.aarp.org/pri/topics/technology/internet-media-devices/2025-technology-trends-older-adults/)
- [WHO Age-Friendly World](https://extranet.who.int/agefriendlyworld/)
    """)

# --- Agents page
if page=="Agents (Clone)":
    st.header("Age-Friendly Clone Agent")
    url = st.text_input("URL to clone", "https://example.com")
    scale = st.slider("Text scale",1.0,1.6,1.25,0.05)
    underline = st.checkbox("Underline links",True)
    targets = st.checkbox("Min 44×44 touch targets",True)
    focus = st.checkbox("Strong focus outline",True)
    reduced = st.checkbox("Respect reduced motion",True)

    if st.button("Generate ZIP", type="primary"):
        try:
            html = fetch_html(url)
            css = build_age_friendly_css(scale,underline,targets,focus,reduced)
            fixed, changes = transform_html(html,url,style_css=css)
            zip_bytes = make_zip("index_age_friendly.html", fixed, changes)
            st.download_button("Download Age-Friendly ZIP", zip_bytes, "shuru_age_friendly.zip","application/zip")
            with st.expander("What changed"): [st.write("• "+c) for c in changes]
        except Exception as e:
            st.error(str(e))

# --- Standards page
elif page=="Standards / About":
    show_standards()

# --- Audit page
else:
    st.header("Audit a Website")
    url = st.text_input("URL", "https://example.com")
    if st.button("Run audit"):
        try:
            html = fetch_html(url)
            fixed, changes = transform_html(html,url,style_css=build_age_friendly_css())
            zip_bytes = make_zip("index_age_friendly.html", fixed, changes)
            st.success("Audit complete")
            st.download_button("Download Age-Friendly ZIP", zip_bytes, "shuru_age_friendly.zip","application/zip")
            with st.expander("What changed"): [st.write("• "+c) for c in changes]
        except Exception as e:
            st.error(str(e))

st.markdown("<hr/>", unsafe_allow_html=True)
st.caption("© 2025 InfraJoy Labs — All rights reserved.")Y

