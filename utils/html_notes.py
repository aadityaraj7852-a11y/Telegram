"""
html_notes.py
Telegram ka HTML parse mode sirf limited tags allow karta hai:
b, strong, i, em, u, ins, s, strike, del, span (with class for spoiler),
a (href), code, pre, blockquote.

Ye module admin ke diye gaye HTML note ko:
1. Allowed tags ke andar rakhta hai (baaki sab strip kar deta hai)
2. Telegram ki 4096-character message limit ke hisaab se chunks me todta hai
3. Agar note bahut bada hai to isse .html file bana ke bhejne ka option deta hai
"""

import re

ALLOWED_TAGS = {
    "b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
    "span", "a", "code", "pre", "blockquote"
}

TELEGRAM_MSG_LIMIT = 4000  # thoda buffer rakha 4096 se kam


def sanitize_for_telegram(html_text):
    """
    Bahut simple tag-whitelist sanitizer. Production-grade HTML
    sanitizer nahi hai, lekin admin-only input ke liye (jo already
    trusted hai) practical hai — koi bhi tag jo allowed list me
    nahi hai use strip kar deta hai, content rakhta hai.
    """
    def replace_tag(match):
        tag_content = match.group(0)
        tag_name_match = re.match(r"</?([a-zA-Z0-9]+)", tag_content)
        if not tag_name_match:
            return ""
        tag_name = tag_name_match.group(1).lower()
        if tag_name in ALLOWED_TAGS:
            return tag_content
        return ""  # strip disallowed tag, keep inner text via normal flow

    cleaned = re.sub(r"<[^>]+>", replace_tag, html_text)
    return cleaned.strip()


def chunk_message(text, limit=TELEGRAM_MSG_LIMIT):
    """Telegram message limit ke hisaab se text ko split karta hai,
    HTML tags ko beech me tootne se bachane ki koshish karte hue
    (simple paragraph/line-based split)."""
    if len(text) <= limit:
        return [text]

    chunks = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > limit:
            if current:
                chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)
    return chunks


def build_note_html_file(title, content_html):
    """Poora standalone HTML file banata hai (download/preview ke liye)"""
    return f"""<!DOCTYPE html>
<html lang="hi">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  body {{ font-family: -apple-system, Arial, sans-serif; max-width: 700px;
          margin: 20px auto; padding: 0 16px; line-height: 1.6; color: #222; }}
  h1 {{ color: #2b6cb0; }}
  blockquote {{ border-left: 4px solid #2b6cb0; margin: 0; padding-left: 12px; color: #555; }}
  code {{ background: #f0f0f0; padding: 2px 6px; border-radius: 4px; }}
  pre {{ background: #f0f0f0; padding: 12px; border-radius: 8px; overflow-x: auto; }}
</style>
</head>
<body>
<h1>{title}</h1>
{content_html}
</body>
</html>"""
