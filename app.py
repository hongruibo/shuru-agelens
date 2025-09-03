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
