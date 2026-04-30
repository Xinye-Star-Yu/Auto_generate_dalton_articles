"""
Launches Claude Code to generate a scientific summary article.
Creates a dated output folder with deliverables matching the template.

Usage:
    python generate.py
"""

import csv
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path


def app_base_dir() -> Path:
    """Directory used for writable runtime files and article outputs."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_base_dir() -> Path:
    """Directory used for bundled read-only files in a PyInstaller build."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", app_base_dir()))
    return app_base_dir()


BASE_DIR = app_base_dir()
RESOURCE_DIR = resource_base_dir()


def ensure_runtime_file(filename: str) -> Path:
    target = BASE_DIR / filename
    source = RESOURCE_DIR / filename
    if not target.exists() and source.exists() and source != target:
        shutil.copy2(source, target)
    return target


def find_template_pdf() -> Path:
    for filename in ("template_article.pdf", "template_output.pdf"):
        for directory in (BASE_DIR, RESOURCE_DIR):
            candidate = directory / filename
            if candidate.exists():
                return candidate
    return BASE_DIR / "template_article.pdf"


ensure_runtime_file("Duplication_Check_Dalton.csv")
ensure_runtime_file("template_output.pdf")
TEMPLATE_PDF = find_template_pdf()
DUP_CSV = BASE_DIR / "Duplication_Check_Dalton.csv"


def normalize_duplication_csv() -> None:
    """Keep the DOI history CSV limited to doi_norm,date columns."""
    if not DUP_CSV.exists():
        with open(DUP_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["doi_norm", "date"])
        return

    with open(DUP_CSV, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = [
            {
                "doi_norm": (row.get("doi_norm") or "").strip(),
                "date": (row.get("date") or "").strip(),
            }
            for row in reader
            if (row.get("doi_norm") or "").strip()
        ]
        if reader.fieldnames == ["doi_norm", "date"]:
            return

    with open(DUP_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["doi_norm", "date"])
        writer.writeheader()
        writer.writerows(rows)


normalize_duplication_csv()
NOTE_SECTION_HTML = """<section aria-labelledby="note">
 <h2 id="note">Note</h2>
 <p>
 This blog post summarizes findings from the above-cited research. Figures are adapted from the original publication. For full details, please refer to the source article.
 </p>
 <p>
 By Xinye Yu, Dalton Bioanalytics, specializing in multiomics analysis
 </p>
</section>"""

# Full article generation instructions (formerly prompt.txt)
INSTRUCTIONS = """\
Create a scientific summary review in HTML for a scientific scholarly article that you first identify yourself. Use the template below as the formatting and structure model. Match the template as closely as possible in layout and section order, but write all content in fully original wording.

Article selection rules:

You must first find a scientific scholarly article on your own
The article must be related to at least one of the following: multiomics, metabolomics, proteomics, or transcriptomics
The article must include at least one figure
The article must include a DOI link
The article must be a real scholarly scientific publication that has been formally published (not a preprint, manuscript, or ahead-of-print version)
Prioritize recent articles: prefer articles published within the last 6 months, and strongly prefer the most recently published articles available
If an article does not satisfy all of these conditions, skip it and continue searching until you find one that does

File and folder requirements:

Create a folder for the output for each article
The folder name must be the date the article was pulled, in YYYY-MM-DD format
Save all deliverables inside that folder

Deliverables:

A pdf file containing the html code, url slug, seo page title, a meta description, image alt text, and Wix-ready structured data markup, in the format shown in the template
The image pulled from Figure 1 of the selected article

Requirements:

Target length: about 600 to 700 words
This is a writing target, not a hard pass/fail requirement
No em dashes
No hyperlinks anywhere in the output HTML
Do not plagiarize the paper or the template
Use your own wording throughout
Keep the Note section exactly identical to the template
Find the paper's citation from the publication itself and include it in APA format in the Citation section
Include Wix-ready structured data markup in JSON-LD format after the metadata

Structure:

Follow this exact two-part structure: <!-- HTML Part 1 (Title -> End of Key Findings) --> <!-- HTML Part 2 (Figure Caption -> End) -->
The local automation script will hard-code the PDF layout as a two-column table matching template_article.pdf:
The table is rendered as four bordered cells: top-left "Part 1", top-right "Part 2", bottom-left Part 1 source text, and bottom-right Part 2 source text. URL/SEO/meta/image-alt text appears underneath, and Wix-ready structured data markup is attached after that metadata block.

Part 1 must include, in this order:

A new original title written in your own words
One short introductory paragraph under the title
One subsection
A Key Findings section
The Key Findings section must be the only section that uses bullet points
End Part 1 at <!-- End of Key Findings -->

Part 2 must include, in this order:

A figure caption based on Figure 1 from the selected article
The figure caption must always be based on Figure 1
The figure caption must follow the same citation style used in the template
After the figure caption, include exactly 3 small subsections only
Then include Conclusion, Citation, and Note
Do not add a large Part 2 title
Do not add nested subsections
All Part 2 headings, including the 3 subsections, Conclusion, Citation, and Note, should use the same heading size

Important:

The article title you create must be original and not copied from the paper
The selected article must satisfy all article selection rules above
If the article does not have Figure 1, or does not have a DOI, or is not related to multiomics, metabolomics, proteomics, or transcriptomics, skip it
The Figure 1 image itself must be included as a deliverable and saved in the output folder
The Note section must remain identical to the template
The template controls the formatting, but the wording should be original
Use the publication itself to determine the correct citation, and format that citation in APA style
The structured data markup must use one <script type="application/ld+json"> tag, contain one JSON-LD object, and be suitable for a Wix Blog article page
Keep structured data values concise so the markup remains easy to copy from the PDF

Template to follow is the TEMPLATE FILE path listed above.\
"""


def load_used_dois():
    """Load already-used DOIs from the duplication check CSV."""
    dois = set()
    if DUP_CSV.exists():
        with open(DUP_CSV, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                dois.add(row["doi_norm"].strip().lower())
    return dois


def create_next_output_dir(run_date: date | str | None = None) -> Path:
    """Create and return the next YYYY-MM-DD-N output folder."""
    if run_date is None:
        date_part = date.today().isoformat()
    elif isinstance(run_date, date):
        date_part = run_date.isoformat()
    else:
        date_part = str(run_date)

    n = 1
    while True:
        output_dir = BASE_DIR / f"{date_part}-{n}"
        try:
            output_dir.mkdir()
            return output_dir
        except FileExistsError:
            n += 1


def build_prompt(output_dir: Path, used_dois: set, target_doi: str | None = None) -> str:
    doi_list = "\n".join(sorted(used_dois))

    if target_doi:
        find_article_block = f"""1. USE THE SPECIFIED ARTICLE
   - You MUST use the article with DOI: {target_doi}
   - Look up this DOI and retrieve the article details.
   - The article MUST have: at least one figure and be a real publication.
   - If you cannot access this article, report the issue clearly."""
    else:
        find_article_block = """1. FIND AN ARTICLE
   - Search PubMed or the web for a real, published scholarly article related to multiomics, metabolomics, proteomics, or transcriptomics.
   - The article MUST have: a DOI, at least one figure, and be a real publication.
   - The article's DOI must NOT be in the already-used list above.
   - If the first article you find doesn't qualify, keep searching until you find one that does."""

    return f"""You are generating a scientific summary review article for Dalton Bioanalytics.

WORKING DIRECTORY: {output_dir}
All output files MUST be saved inside this directory. It already exists.

TEMPLATE FILE: {TEMPLATE_PDF}
Read this PDF first. It contains two example articles that show the exact formatting, structure, and layout you must follow.

FULL INSTRUCTIONS:
{INSTRUCTIONS}

ALREADY-USED DOIs (do NOT pick any of these):
{doi_list}

STEP-BY-STEP WORKFLOW:

{find_article_block}

2. READ THE TEMPLATE
   - Read {TEMPLATE_PDF} to see the exact HTML structure, formatting, and layout.
   - Your output must match this template closely in structure and heading hierarchy.

4. DOWNLOAD FIGURE 1
   - Find and download the Figure 1 image from the article.
   - Save it inside {output_dir} with a descriptive filename (e.g., figure1.png or figure1.jpg).
   - If you cannot directly download it, try accessing the article's HTML page and finding the figure image URL.

5. WRITE THE HTML CONTENT
   - Write the full HTML summary review following the template structure exactly.
   - Two-part structure with comments: <!-- HTML Part 1 (Title -> End of Key Findings) --> and <!-- HTML Part 2 (Figure Caption -> End) -->
   - Part 1: original title (in <em> tags inside <h1>), one intro paragraph, one subsection with <h2>, Key Findings section with bullet points, then <!-- End of Key Findings -->
   - The intro paragraph must be inside <section aria-labelledby="abstract"> and must NOT have an Abstract heading or any <h2> tag
   - Do not wrap one <section> inside another <section>; every content section should be a direct sibling
   - Part 2: figure caption based on Figure 1 (with citation style matching template), exactly 3 small subsections (each with <h2>), then Conclusion, Citation, and Note sections (all with <h2>)
   - The figure section must use <section aria-labelledby="figure1">, <figure>, and <figcaption>, and the caption must start with <em>Figure 1.</em>
   - The Note section must be EXACTLY:
     <section aria-labelledby="note">
      <h2 id="note">Note</h2>
      <p>
     This blog post summarizes findings from the above-cited research. Figures are adapted from the original publication. For full details, please refer to the source article.
      </p>
      <p>
     By Xinye Yu, Dalton Bioanalytics, specializing in multiomics analysis
      </p>
     </section>
   - Target length: 600-700 words (the HTML text content, not counting tags). This is a target, not a hard pass/fail requirement.
   - No em dashes anywhere
   - No hyperlinks (<a> tags) anywhere in the HTML
   - Citation in APA format from the publication itself
   - All wording must be original, not copied from the paper or template
   - After the HTML, add the metadata group and a Wix-ready structured data markup block in JSON-LD format
   - The metadata group must contain only these labels, in this order: URL slug, SEO page title, Meta description, Image alt text
   - Do not try to create the visual two-column layout yourself. The local automation script will split Part 1 and Part 2 and render the PDF layout.

6. PREPARE THE PDF CONTENT
   - Generate the complete variable source content for the PDF. Do NOT create article_output.pdf yourself. The local automation script will create the PDF from your final marked output using the template's two-column layout.
   - The final marked content must contain this source content in this exact order:
     HTML Part 1
     HTML Part 2
     URL slug: <your-url-slug>
     SEO page title: <Your SEO Page Title>
     Meta description: <Your meta description>
     Image alt text: <Your image alt text>
     Structured data markup:
     <script type="application/ld+json">
     {{
       "@context": "https://schema.org",
       "@type": "BlogPosting",
       "headline": "<SEO page title or article title>",
       "description": "<meta description>",
       "image": "<Figure 1 image filename or final image URL>",
       "author": {{
         "@type": "Person",
         "name": "Xinye Yu"
       }},
       "publisher": {{
         "@type": "Organization",
         "name": "Dalton Bioanalytics"
       }},
       "datePublished": "{date.today().isoformat()}",
       "dateModified": "{date.today().isoformat()}",
       "mainEntityOfPage": {{
       "@type": "WebPage",
       "@id": "<final page URL if known, otherwise URL slug>"
     }},
       "citation": "https://doi.org/<selected DOI>"
     }}
     </script>
   - The structured data must use exactly one <script type="application/ld+json"> tag and one main Schema.org type
   - Do not put any HTML tags inside the JSON-LD object
   - Keep long JSON-LD values short enough to copy cleanly from the PDF; use the DOI URL for the structured data citation instead of the full APA citation
   - Keep the structured data markup under 7,000 characters
   - Do NOT create content.txt, make_pdf.py, or any other temporary content files.

7. VERIFY AND CLEAN UP
   - Confirm these files exist in {output_dir}:
     The Figure 1 image file
   - Delete any temporary or artifact files (e.g., content.txt, make_pdf.py) so only the PDF and image remain.
   - The local automation script will create article_output.pdf after your final marked output is captured.

8. FINAL OUTPUT
   - Print the full HTML content (everything that went into the PDF) between these exact markers:
     ---BEGIN_CONTENT---
     (full HTML + metadata here)
     ---END_CONTENT---
   - Then print the DOI of the selected article as the very last line of your output, in this exact format:
     SELECTED_DOI: 10.xxxx/xxxxx

IMPORTANT REMINDERS:
- All files go in {output_dir}, nowhere else
- Match the template structure precisely
- The script, not Claude, controls the final PDF formatting
- The final PDF must match the template's title, bordered 2x2 Part 1/Part 2 table, metadata block, and structured-data-at-end layout
- No em dashes (use hyphens or commas instead)
- No hyperlinks in the HTML
- Target 600-700 words total, but do not sacrifice scientific accuracy or required sections just to hit the target
- The figure caption must reference Figure 1 specifically
- Keep the Note section identical to template
- URL slug, SEO page title, meta description, image alt text, and Wix-ready structured data markup go in the PDF after the HTML
"""


def extract_marked_content(claude_stdout: str) -> str:
    """Extract the final HTML, metadata, and structured data block from Claude output."""
    if "---BEGIN_CONTENT---" not in claude_stdout or "---END_CONTENT---" not in claude_stdout:
        return ""
    start = claude_stdout.index("---BEGIN_CONTENT---") + len("---BEGIN_CONTENT---")
    end = claude_stdout.index("---END_CONTENT---")
    return claude_stdout[start:end].strip()


def normalize_note_section(raw_content: str) -> str:
    """Hard-code the template Note section because it must never vary."""
    import re

    return re.sub(
        r"<section\s+aria-labelledby=[\"']note[\"']>.*?</section>",
        NOTE_SECTION_HTML,
        raw_content,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )


def split_template_sections(raw_content: str) -> tuple[str, str, str, str]:
    """Split the final document into the four template blocks."""
    content = raw_content.strip()

    structured_marker = "Structured data markup:"
    structured_idx = content.find(structured_marker)
    if structured_idx != -1:
        before_structured = content[:structured_idx].strip()
        structured_data = content[structured_idx:].strip()
    else:
        before_structured = content
        structured_data = ""

    metadata_marker = "URL slug:"
    metadata_idx = before_structured.find(metadata_marker)
    if metadata_idx != -1:
        article_html = before_structured[:metadata_idx].strip()
        metadata = before_structured[metadata_idx:].strip()
    else:
        article_html = before_structured.strip()
        metadata = ""

    end_marker = "<!-- End of Key Findings -->"
    end_idx = article_html.find(end_marker)
    part2_idx = article_html.find("<!-- HTML Part 2")
    if end_idx != -1:
        part1 = article_html[: end_idx + len(end_marker)].strip()
        part2 = article_html[end_idx + len(end_marker) :].strip()
    elif part2_idx != -1:
        part1 = article_html[:part2_idx].strip()
        part2 = article_html[part2_idx:].strip()
    else:
        part1 = article_html
        part2 = ""

    return part1, part2, metadata, structured_data


def normalize_generated_content(raw_content: str) -> str:
    """Normalize fixed template content while preserving Claude's article-specific text."""
    return normalize_note_section(raw_content).strip()


def create_pdf_deliverable(output_dir: Path, content: str) -> None:
    """Create article_output.pdf locally using the template's two-column layout."""
    import html
    import re
    import textwrap

    from fpdf import FPDF

    content = normalize_generated_content(content)
    part1, part2, metadata, structured_data = split_template_sections(content)

    def pdf_safe(text: str) -> str:
        replacements = {
            "\u2018": "'",
            "\u2019": "'",
            "\u201c": '"',
            "\u201d": '"',
            "\u2013": "-",
            "\u2014": "-",
            "\u2192": "->",
            "\xa0": " ",
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text.encode("latin-1", "replace").decode("latin-1")

    def wrap_source_lines(text: str, width: int) -> list[str]:
        wrapped_lines = []
        for raw_line in text.splitlines():
            line = pdf_safe(raw_line.rstrip())
            if not line:
                wrapped_lines.append("")
                continue
            indent_len = len(line) - len(line.lstrip(" "))
            indent = line[:indent_len]
            continuation_indent = indent + "  " if indent_len < 20 else indent
            wrapped = textwrap.wrap(
                line,
                width=width,
                replace_whitespace=False,
                drop_whitespace=False,
                break_long_words=True,
                break_on_hyphens=False,
                subsequent_indent=continuation_indent,
            )
            wrapped_lines.extend(wrapped or [""])
        return wrapped_lines

    def extract_title(source: str) -> str:
        title_match = re.search(r"<h1[^>]*>(.*?)</h1>", source, re.IGNORECASE | re.DOTALL)
        if not title_match:
            return "Generated Article"
        title = re.sub(r"<[^>]+>", "", title_match.group(1))
        return html.unescape(title).strip() or "Generated Article"

    def parse_metadata_block(source: str) -> dict[str, str]:
        labels = ["URL slug", "SEO page title", "Meta description", "Image alt text"]
        values: dict[str, str] = {}
        current_label = None
        current_value: list[str] = []

        for raw_line in source.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            matched_label = None
            for label in labels:
                prefix = f"{label}:"
                if line.startswith(prefix):
                    matched_label = label
                    line = line[len(prefix) :].strip()
                    break

            if matched_label:
                if current_label:
                    values[current_label] = " ".join(current_value).strip()
                current_label = matched_label
                current_value = [line]
            elif current_label:
                current_value.append(line)

        if current_label:
            values[current_label] = " ".join(current_value).strip()
        return values

    def ensure_space(pdf: FPDF, needed_height: float, margin: float) -> None:
        if pdf.get_y() + needed_height > pdf.h - margin:
            pdf.add_page()
            pdf.set_y(margin)

    def write_labeled_metadata(pdf: FPDF, label: str, value: str, margin: float, page_width: float) -> None:
        if not value:
            return
        ensure_space(pdf, 12, margin)
        pdf.set_x(margin)
        pdf.set_font("Helvetica", "B", 12)
        pdf.write(6.0, pdf_safe(f"{label}: "))
        pdf.set_font("Helvetica", "", 12)
        pdf.write(6.0, pdf_safe(value))
        pdf.ln(6.8)

    pdf = FPDF(unit="mm", format="Letter")
    margin = 25.4
    pdf.set_margins(margin, margin, margin)
    pdf.set_auto_page_break(False)
    pdf.add_page()

    page_width = pdf.w - (2 * margin)
    table_width = page_width
    col_width = table_width / 2
    header_height = 7.0
    code_size = 3.0
    line_height = 1.35
    content_padding = 2.0

    pdf.set_font("Helvetica", size=13)
    pdf.set_xy(margin, margin)
    pdf.multi_cell(page_width, 6.5, pdf_safe(extract_title(part1)), align="L")
    pdf.ln(5)

    left_lines = wrap_source_lines(part1, 108)
    right_lines = wrap_source_lines(part2, 108)
    left_idx = 0
    right_idx = 0
    first_table = True

    while left_idx < len(left_lines) or right_idx < len(right_lines):
        if not first_table:
            pdf.add_page()
            pdf.set_y(margin)

        table_top = pdf.get_y()
        content_top = table_top + header_height + 3.0
        max_bottom = pdf.h - margin
        max_rows = max(1, int((max_bottom - content_top - 2.0) / line_height))
        remaining_rows = max(len(left_lines) - left_idx, len(right_lines) - right_idx)
        rows = min(max_rows, remaining_rows)
        table_bottom = content_top + (rows * line_height) + 2.0

        # Draw a true 2x2 table: header cells above source-code cells.
        pdf.set_draw_color(0, 0, 0)
        pdf.set_line_width(0.45)
        pdf.rect(margin, table_top, table_width, table_bottom - table_top)
        pdf.line(margin, table_top + header_height, margin + table_width, table_top + header_height)
        pdf.line(margin + col_width, table_top, margin + col_width, table_bottom)

        pdf.set_font("Helvetica", size=6)
        pdf.set_xy(margin + content_padding, table_top + 2)
        pdf.cell(col_width - (2 * content_padding), 3, "Part 1")
        pdf.set_xy(margin + col_width + content_padding, table_top + 2)
        pdf.cell(col_width - (2 * content_padding), 3, "Part 2")

        # Write one column at a time so PDF selection can stay within a column.
        pdf.set_font("Helvetica", size=code_size)
        y = content_top
        for row in range(rows):
            if left_idx + row < len(left_lines):
                pdf.set_xy(margin + content_padding, y)
                pdf.cell(col_width - (2 * content_padding), line_height, left_lines[left_idx + row])
            y += line_height

        y = content_top
        for row in range(rows):
            if right_idx + row < len(right_lines):
                pdf.set_xy(margin + col_width + content_padding, y)
                pdf.cell(col_width - (2 * content_padding), line_height, right_lines[right_idx + row])
            y += line_height

        left_idx += rows
        right_idx += rows
        first_table = False
        pdf.set_y(table_bottom + 8.5)

    metadata_values = parse_metadata_block(metadata)
    if metadata_values:
        ensure_space(pdf, 42, margin)
        for label in ["URL slug", "SEO page title", "Meta description", "Image alt text"]:
            write_labeled_metadata(pdf, label, metadata_values.get(label, ""), margin, page_width)

    if structured_data:
        ensure_space(pdf, 22, margin)
        pdf.ln(5)
        structured_lines = structured_data.splitlines()
        structured_label = structured_lines[0].strip()
        structured_body = "\n".join(structured_lines[1:])

        pdf.set_x(margin)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(page_width, 6, pdf_safe(structured_label))
        pdf.ln(8)

        pdf.set_font("Courier", size=5.2)
        for line in wrap_source_lines(structured_body, 135):
            ensure_space(pdf, 2.7, margin)
            if line == "":
                pdf.ln(2.7)
                continue
            pdf.set_x(margin)
            pdf.cell(page_width, 2.7, line)
            pdf.ln(2.7)

    pdf.output(str(output_dir / "article_output.pdf"))


def validate_outputs(
    output_dir: Path,
    used_dois_before: set,
    claude_stdout: str = "",
    content: str | None = None,
) -> list:
    """Validate all deliverables. Returns list of failure messages (empty = all passed)."""
    import json
    import re

    failures = []
    image_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".tif", ".tiff"}

    # --- 1. Check output folder exists ---
    if not output_dir.is_dir():
        failures.append(f"FAIL: Output folder does not exist: {output_dir}")
        return failures

    files = list(output_dir.iterdir())

    # --- 2. Check PDF exists and is non-trivial ---
    pdf_file = output_dir / "article_output.pdf"
    if not pdf_file.exists():
        failures.append("FAIL: article_output.pdf not found")
    elif pdf_file.stat().st_size < 500:
        failures.append(f"FAIL: article_output.pdf too small ({pdf_file.stat().st_size} bytes)")
    else:
        try:
            pdf_text_result = subprocess.run(
                ["pdftotext", "-layout", str(pdf_file), "-"],
                text=True,
                capture_output=True,
                timeout=20,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            print("  PDF text validation skipped: pdftotext is unavailable")
        else:
            if pdf_text_result.returncode == 0:
                pdf_text = pdf_text_result.stdout
                if len(pdf_text.strip()) < 1000:
                    failures.append("FAIL: article_output.pdf text extraction is unexpectedly short")
                for marker in [
                    "Part 1",
                    "Part 2",
                    "<!-- HTML Part 1",
                    "<!-- HTML Part 2",
                    "URL slug:",
                    "SEO page title:",
                    "Meta description:",
                    "Image alt text:",
                    "Structured data markup:",
                ]:
                    if marker not in pdf_text:
                        failures.append(f"FAIL: article_output.pdf is missing '{marker}' in extracted text")
                part1_idx = pdf_text.find("Part 1")
                part2_idx = pdf_text.find("Part 2")
                metadata_idx = pdf_text.find("URL slug:")
                structured_idx = pdf_text.find("Structured data markup:")
                if min(part1_idx, part2_idx, metadata_idx, structured_idx) == -1:
                    pass
                elif not (part1_idx < metadata_idx < structured_idx and part2_idx < metadata_idx):
                    failures.append("FAIL: PDF text order does not match template table, metadata, structured data")
            else:
                print("  PDF text validation skipped: pdftotext could not read the PDF")

            try:
                raw_pdf_text_result = subprocess.run(
                    ["pdftotext", "-raw", str(pdf_file), "-"],
                    text=True,
                    capture_output=True,
                    timeout=20,
                )
            except subprocess.TimeoutExpired:
                print("  PDF raw text stream validation skipped: pdftotext timed out")
            else:
                if raw_pdf_text_result.returncode == 0:
                    raw_pdf_text = raw_pdf_text_result.stdout
                    raw_order_markers = [
                        "<!-- HTML Part 1",
                        "<!-- End of Key Findings -->",
                        "<!-- HTML Part 2",
                        "URL slug:",
                        "Structured data markup:",
                    ]
                    raw_positions = [raw_pdf_text.find(marker) for marker in raw_order_markers]
                    if all(position != -1 for position in raw_positions) and raw_positions != sorted(raw_positions):
                        failures.append(
                            "FAIL: PDF raw text stream does not keep Part 1 separate before Part 2"
                        )

    # --- 3. Check Figure 1 image exists ---
    images = [f for f in files if f.suffix.lower() in image_exts]
    if not images:
        failures.append("FAIL: No Figure 1 image file found")
    else:
        for img in images:
            if img.stat().st_size < 1000:
                failures.append(f"FAIL: Image {img.name} too small ({img.stat().st_size} bytes)")

    # --- 4. Check no artifact files remain ---
    artifact_names = {"content.txt", "make_pdf.py"}
    found_artifacts = [f.name for f in files if f.name in artifact_names]
    if found_artifacts:
        failures.append(f"FAIL: Artifact files still present: {', '.join(found_artifacts)}")

    # --- 5. Check only expected files exist (PDF + images) ---
    allowed_exts = {".pdf"} | image_exts
    unexpected = [f.name for f in files if f.suffix.lower() not in allowed_exts]
    if unexpected:
        failures.append(f"FAIL: Unexpected files in output folder: {', '.join(unexpected)}")

    # --- 6. Validate final HTML/source content ---
    content = normalize_generated_content(content or extract_marked_content(claude_stdout))
    if "<!-- HTML Part 1" not in content:
        failures.append("FAIL: Could not find HTML content in Claude output for validation")
    else:
        part1, part2, _, _ = split_template_sections(content)

        # Part 1 / Part 2 structure
        if "<!-- End of Key Findings -->" not in content:
            failures.append("FAIL: Missing <!-- End of Key Findings --> comment")
        if "<!-- HTML Part 2" not in content:
            failures.append("FAIL: Missing <!-- HTML Part 2 --> comment")
        if re.search(r"<section>\s*<section", content, re.IGNORECASE):
            failures.append("FAIL: Content contains nested wrapper <section> tags")

        # Key HTML elements
        if not re.search(r"<h1(?:\s[^>]*)?>", content, re.IGNORECASE):
            failures.append("FAIL: Missing <h1> title")
        if "<h2" not in content.lower():
            failures.append("FAIL: Missing <h2> sections")
        abstract_match = re.search(
            r"<section\s+aria-labelledby=[\"']abstract[\"'][^>]*>(.*?)</section>",
            part1,
            re.IGNORECASE | re.DOTALL,
        )
        if not abstract_match:
            failures.append("FAIL: Missing abstract intro section")
        elif re.search(r"<h[1-6]\b", abstract_match.group(1), re.IGNORECASE):
            failures.append("FAIL: Abstract intro section must not contain a heading")
        if not re.search(
            r"<section\s+aria-labelledby=[\"']figure1[\"'][^>]*>.*?<figure>.*?<figcaption>\s*<em>Figure 1\.</em>",
            part2,
            re.IGNORECASE | re.DOTALL,
        ):
            failures.append("FAIL: Figure 1 section must use the template figure/figcaption structure")

        # Key Findings with bullet points
        if "<ul>" not in content.lower() or "<li>" not in content.lower():
            failures.append("FAIL: Missing bullet points in Key Findings")

        # Required sections
        for section in ["Key Findings", "Conclusion", "Citation", "Note"]:
            if section.lower() not in content.lower():
                failures.append(f"FAIL: Missing '{section}' section")

        # Note section content
        if "This blog post summarizes findings from the above-cited research" not in content:
            failures.append("FAIL: Note section text does not match template")
        if "By Xinye Yu, Dalton Bioanalytics, specializing in multiomics analysis" not in content:
            failures.append("FAIL: Note section byline does not match template")
        if NOTE_SECTION_HTML not in content:
            failures.append("FAIL: Note section HTML does not exactly match template")

        # Figure caption
        if "Figure 1" not in content:
            failures.append("FAIL: Missing Figure 1 caption")

        # No em dashes
        if "\u2014" in content:
            failures.append("FAIL: Content contains em dashes")

        # No hyperlinks
        if "<a " in content.lower() or "href=" in content.lower():
            failures.append("FAIL: Content contains hyperlinks")

        # Metadata
        if "URL slug:" not in content:
            failures.append("FAIL: Missing URL slug")
        if "SEO page title:" not in content:
            failures.append("FAIL: Missing SEO page title")
        if "Meta description:" not in content:
            failures.append("FAIL: Missing Meta description")
        if "Image alt text:" not in content:
            failures.append("FAIL: Missing Image alt text")
        if "Structured data markup:" not in content:
            failures.append("FAIL: Missing Structured data markup")

        script_tags = re.findall(
            r"<script\s+type=[\"']application/ld\+json[\"']>\s*(.*?)\s*</script>",
            content,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if len(script_tags) != 1:
            failures.append(
                f"FAIL: Expected exactly one JSON-LD script tag, found {len(script_tags)}"
            )
        else:
            json_ld = script_tags[0].strip()
            full_script_match = re.search(
                r"<script\s+type=[\"']application/ld\+json[\"']>.*?</script>",
                content,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if full_script_match and len(full_script_match.group(0)) >= 7000:
                failures.append("FAIL: Structured data markup is 7,000 characters or longer")
            if "<" in json_ld or ">" in json_ld:
                failures.append("FAIL: JSON-LD object contains HTML tags or angle brackets")
            try:
                structured_data = json.loads(json_ld)
            except json.JSONDecodeError as exc:
                failures.append(f"FAIL: Structured data markup is not valid JSON: {exc}")
            else:
                if structured_data.get("@context") != "https://schema.org":
                    failures.append("FAIL: Structured data @context must be https://schema.org")
                if structured_data.get("@type") not in {"BlogPosting", "Article"}:
                    failures.append("FAIL: Structured data @type must be BlogPosting or Article")
                for field in [
                    "headline",
                    "description",
                    "image",
                    "author",
                    "publisher",
                    "datePublished",
                    "dateModified",
                    "mainEntityOfPage",
                    "citation",
                ]:
                    if field not in structured_data:
                        failures.append(f"FAIL: Structured data missing '{field}'")

        # Word count (strip HTML tags, stop at metadata)
        text_only = re.sub(r"<[^>]+>", "", content)
        for marker in ["URL slug:", "SEO page title:"]:
            idx = text_only.find(marker)
            if idx != -1:
                text_only = text_only[:idx]
                break
        word_count = len(text_only.split())
        print(f"  Word count: {word_count} (target 600-700, not enforced)")

        # Count h2 sections in Part 2 (after End of Key Findings)
        part2_start = content.find("<!-- End of Key Findings -->")
        if part2_start != -1:
            part2 = content[part2_start:]
            h2_count = len(re.findall(r"<h2", part2, re.IGNORECASE))
            if h2_count < 6:
                failures.append(f"FAIL: Part 2 has only {h2_count} <h2> sections (expected at least 6)")

    # --- 7. Check DOI was appended to CSV ---
    current_dois = load_used_dois()
    new_dois = current_dois - used_dois_before
    if not new_dois:
        failures.append("FAIL: No new DOI was appended to the duplication CSV")
    else:
        print(f"  New DOI added: {new_dois.pop()}")

    return failures


MAX_RETRIES = 3

# Patterns in Claude output that indicate a non-retryable token/context exhaustion.
_TOKEN_EXHAUSTION_PATTERNS = [
    "max_tokens",
    "maximum context length",
    "context window",
    "token limit",
    "conversation is too long",
    "context length exceeded",
    "ran out of",
]


def is_token_exhaustion(stdout: str, stderr: str) -> bool:
    """Detect whether the Claude run failed due to token/context exhaustion."""
    combined = (stdout + "\n" + stderr).lower()
    for pattern in _TOKEN_EXHAUSTION_PATTERNS:
        if pattern in combined:
            return True
    # BEGIN without END means output was truncated mid-generation
    if "---BEGIN_CONTENT---" in stdout and "---END_CONTENT---" not in stdout:
        return True
    return False


def remove_doi_from_csv(doi: str) -> None:
    """Remove a DOI from the duplication CSV so it doesn't block future runs."""
    if not DUP_CSV.exists() or not doi:
        return
    with open(DUP_CSV, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = [row for row in reader if row.get("doi_norm", "").strip().lower() != doi.lower()]
    with open(DUP_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["doi_norm", "date"])
        writer.writeheader()
        writer.writerows(rows)


def cleanup_failed_attempt(output_dir: Path, selected_doi: str | None) -> None:
    """Delete the output folder and remove the DOI from CSV after a failed attempt."""
    if selected_doi:
        remove_doi_from_csv(selected_doi)
        print(f"Removed DOI from duplication CSV: {selected_doi}")
    if output_dir.is_dir():
        import shutil as _shutil
        _shutil.rmtree(output_dir, ignore_errors=True)
        print(f"Deleted failed output folder: {output_dir}")


def generate_one(target_doi: str | None = None) -> tuple[bool, bool, Path, str | None]:
    """Run a single generation attempt.

    Returns (success, retryable, output_dir, selected_doi).
    """
    today = date.today().isoformat()
    output_dir = create_next_output_dir(today)
    print(f"Output folder: {output_dir}")

    used_dois = load_used_dois()
    print(f"Loaded {len(used_dois)} already-used DOIs")

    if target_doi:
        print(f"Target DOI: {target_doi}")

    prompt = build_prompt(output_dir, used_dois, target_doi=target_doi)

    print("Launching Claude Code...\n")
    cmd = [
        "claude",
        "--model", "opus",
        "--dangerously-skip-permissions",
        "-p", prompt,
        "--verbose",
    ]

    result = subprocess.run(
        cmd,
        cwd=str(output_dir),
        text=True,
        capture_output=True,
    )

    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr, file=sys.stderr)

    # Check for token exhaustion before anything else
    if is_token_exhaustion(result.stdout, result.stderr):
        print("\nERROR: Claude ran out of tokens or context. This is not retryable.")
        return False, False, output_dir, None

    # Extract DOI from output
    selected_doi = None
    for line in result.stdout.splitlines():
        if line.strip().startswith("SELECTED_DOI:"):
            selected_doi = line.split(":", 1)[1].strip().lower()
            break

    # Hard duplicate check
    if selected_doi and selected_doi in used_dois:
        print(f"\nERROR: DOI {selected_doi} is already in the duplication check CSV. "
              "Claude selected a duplicate article. Not appending.")
        selected_doi = None

    # Append to duplication CSV
    if selected_doi:
        with open(DUP_CSV, "rb") as f:
            f.seek(0, 2)
            if f.tell() > 0:
                f.seek(-1, 2)
                if f.read(1) != b"\n":
                    with open(DUP_CSV, "a", encoding="utf-8") as fa:
                        fa.write("\n")
        with open(DUP_CSV, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([selected_doi, today])
        print(f"\nAppended DOI to duplication check: {selected_doi}")
    elif selected_doi is None:
        print("\nWARNING: Could not extract a valid DOI from output. Check results manually.")

    # Create PDF
    content = extract_marked_content(result.stdout)
    if content:
        content = normalize_generated_content(content)
        create_pdf_deliverable(output_dir, content)
        print("\nCreated PDF deliverable: article_output.pdf")
    else:
        print("\nWARNING: Could not extract marked content. PDF was not created locally.")

    # List files
    print(f"\nFiles in {output_dir}:")
    for f in sorted(output_dir.iterdir()):
        print(f"  {f.name} ({f.stat().st_size} bytes)")

    # Validate
    print("\n--- VALIDATION ---")
    failures = validate_outputs(output_dir, used_dois, result.stdout, content)
    if failures:
        print(f"\n{len(failures)} check(s) failed:")
        for f in failures:
            print(f"  {f}")
        return False, True, output_dir, selected_doi

    print("\nAll checks passed!")
    return True, True, output_dir, selected_doi


def main(target_doi: str | None = None):
    for attempt in range(1, MAX_RETRIES + 1):
        if attempt > 1:
            print(f"\n{'='*60}")
            print(f"RETRY attempt {attempt} of {MAX_RETRIES}")
            print(f"{'='*60}\n")

        success, retryable, output_dir, selected_doi = generate_one(target_doi=target_doi)

        if success:
            return

        if not retryable:
            print("\nNon-retryable failure. Cleaning up and stopping.")
            cleanup_failed_attempt(output_dir, selected_doi)
            sys.exit(1)

        if attempt < MAX_RETRIES:
            print(f"\nAttempt {attempt} failed. Cleaning up and retrying...")
            cleanup_failed_attempt(output_dir, selected_doi)
        else:
            print(f"\nAll {MAX_RETRIES} attempts failed. Cleaning up last attempt...")
            cleanup_failed_attempt(output_dir, selected_doi)
            sys.exit(1)


if __name__ == "__main__":
    main()
