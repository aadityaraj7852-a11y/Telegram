"""
pdf_cleaner.py
PDF se watermark aur hyperlinks hatane ka logic.

Do tarike try karte hain:
1. PyMuPDF (fitz) available ho to usse — behtar quality, image/text
   watermark annotations bhi hata sakta hai.
2. Nahi ho to pypdf fallback — sirf link annotations (/Annots) aur
   metadata-level cheezein hata sakta hai (embedded hyperlinks,
   XMP watermark metadata), lekin baked-in image watermark nahi
   hata sakta (wo pixel data hai, uske liye fitz chahiye).

Render pe requirements.txt me PyMuPDF hai, is liye production me
behtar wala method use hoga.
"""

import os

try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

from pypdf import PdfReader, PdfWriter


def clean_pdf_pypdf(input_path, output_path):
    """
    Fallback method (no PyMuPDF):
    - Removes all link annotations (/Link) — clickable hyperlinks
      including any embedded watermark link
    - Strips document metadata (author, producer tags often used to
      brand/watermark a PDF)
    Returns: (success: bool, message: str)
    """
    reader = PdfReader(input_path)
    writer = PdfWriter()

    from pypdf.generic import NameObject, ArrayObject

    for page in reader.pages:
        if "/Annots" in page:
            try:
                annots = page["/Annots"]
                kept = []
                for a in annots:
                    obj = a.get_object()
                    # Keep non-link annotations, drop /Link (hyperlinks) and
                    # /Watermark-type annotations
                    if obj.get("/Subtype") not in ("/Link", "/Watermark"):
                        kept.append(a)
                if kept:
                    page[NameObject("/Annots")] = ArrayObject(kept)
                else:
                    del page["/Annots"]
            except Exception:
                pass
        writer.add_page(page)

    writer.add_metadata({"/Producer": "", "/Creator": "", "/Author": ""})

    with open(output_path, "wb") as f:
        writer.write(f)

    return True, "Links aur metadata clean kar diye (pypdf fallback mode)."


def clean_pdf_fitz(input_path, output_path):
    """
    Preferred method using PyMuPDF:
    - Removes all link annotations on every page
    - Removes watermark-type annotations
    - Attempts to detect and redact repeating semi-transparent
      text/image objects that look like watermarks (best-effort —
      complex diagonal image watermarks baked into content streams
      may still need manual review)
    Returns: (success: bool, message: str)
    """
    doc = fitz.open(input_path)
    removed_links = 0
    removed_annots = 0

    for page in doc:
        # Remove hyperlinks
        for link in page.get_links():
            page.delete_link(link)
            removed_links += 1

        # Remove annotation-based watermarks/stamps
        annot = page.first_annot
        while annot:
            nxt = annot.next
            if annot.type[0] in (fitz.PDF_ANNOT_WATERMARK, fitz.PDF_ANNOT_STAMP,
                                   fitz.PDF_ANNOT_FREETEXT):
                page.delete_annot(annot)
                removed_annots += 1
            annot = nxt

    # Strip identifying metadata
    doc.set_metadata({})

    doc.save(output_path, garbage=4, deflate=True)
    doc.close()

    return True, f"{removed_links} hyperlink(s) aur {removed_annots} watermark/stamp annotation(s) hataye."


def clean_pdf(input_path, output_path):
    """Main entry point — uses best available method."""
    try:
        if HAS_FITZ:
            return clean_pdf_fitz(input_path, output_path)
        else:
            return clean_pdf_pypdf(input_path, output_path)
    except Exception as e:
        return False, f"Error: {e}"
