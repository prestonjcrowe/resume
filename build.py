import markdown
import os
from bs4 import BeautifulSoup
from weasyprint import HTML, CSS

def build_single_page_resume(md_file='resume.md', css_file='style.css', pdf_file='resume.pdf'):
    if not os.path.exists(md_file):
        print(f"Error: {md_file} not found.")
        return

    # 1. Read Markdown content
    with open(md_file, 'r', encoding='utf-8') as f:
        md_content = f.read()

    # 2. Convert Markdown to HTML
    raw_html = markdown.markdown(
        md_content, 
        extensions=['tables', 'fenced_code', 'sane_lists']
    )
    
    # 3. Structure the HTML so style.css can apply the ASCII art and brackets
    soup = BeautifulSoup(raw_html, "html.parser")
    
    # Add [ BRACKETS ] to h2 section headers
    for h2 in soup.find_all("h2"):
        label = h2.get_text(strip=True)
        h2.string = f"[{label}]"
        
    # Wrap the top section in a <header> for CSS ASCII box art
    first_h2 = soup.find("h2")
    header = soup.new_tag("header")
    for el in list(soup.children):
        if el is first_h2:
            break
        header.append(el.extract())
    soup.insert(0, header)
    
    # Add .entry and .first classes to paragraphs starting with <strong> (for CSS margins)
    seen_in_section = False
    for el in soup.children:
        if getattr(el, "name", None) == "h2":
            seen_in_section = False
        elif getattr(el, "name", None) == "p":
            first_child = next((c for c in el.children if getattr(c, "name", None) or str(c).strip()), None)
            if getattr(first_child, "name", None) == "strong":
                el["class"] = ["entry"] + ([] if seen_in_section else ["first"])
                seen_in_section = True

    # Assemble the final HTML document
    html_string = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Resume</title>
    </head>
    <body>
        {str(soup)}
    </body>
    </html>
    """

    # 4. Setup WeasyPrint objects
    html = HTML(string=html_string, base_url=os.path.dirname(os.path.abspath(md_file)))
    base_stylesheets = [CSS(filename=css_file)] if os.path.exists(css_file) else []

    # 5. Iteratively adjust the CSS font-size to force a single page
    font_scale = 1.0
    min_scale = 0.5
    scale_step = 0.05

    print("Generating PDF...")

    while font_scale >= min_scale:
        # Inject a dynamic CSS rule to shrink the text without shrinking the page boundaries
        scale_css = CSS(string=f"html {{ font-size: {font_scale * 100}%; }}")
        
        doc = html.render(stylesheets=base_stylesheets + [scale_css])
        page_count = len(doc.pages)
        
        if page_count == 1:
            doc.write_pdf(pdf_file)
            print(f"Success! PDF built at {pdf_file} (Font scale: {font_scale * 100:.0f}%)")
            return
        
        print(f"Scale {font_scale * 100:.0f}% resulted in {page_count} pages. Scaling down...")
        font_scale -= scale_step

    print("Warning: Could not fit content to a single page without shrinking beyond min_scale.")
    doc.write_pdf(pdf_file)
    print(f"Saved multi-page PDF to {pdf_file}")

if __name__ == '__main__':
    build_single_page_resume()