"""
utils/docx_parser.py
Word (.docx) files ko parse karne ka logic.
- Sirf #Hindi_directions wale questions lega, #English_directions wale ignore.
- FIX: Table (Match the following) ab question me judti hai.
- FIX: Question ke andar line-breaks / multi-line paragraph safe.
- FIX: Options me A-J, "A." / "A)" dono format.
"""
import re
import docx
from docx.text.paragraph import Paragraph
from docx.table import Table


def _iter_blocks(document):
    """Paragraph aur Table ko document ke asli order me deta hai."""
    for child in document.element.body.iterchildren():
        tag = child.tag.split('}')[1]
        if tag == 'p':
            yield Paragraph(child, document)
        elif tag == 'tbl':
            yield Table(child, document)


def _table_to_text(tbl):
    lines = []
    for row in tbl.rows:
        cells = []
        for c in row.cells:
            t = c.text.strip()
            if t and (not cells or cells[-1] != t):  # merged cell ke duplicate hatao
                cells.append(t)
        if cells:
            lines.append("   ➜   ".join(cells))
    return "\n".join(lines)


def parse_docx(file_path):
    doc = docx.Document(file_path)
    parsed_questions = []

    current_q = None
    current_section = "General"
    current_key = None
    process_questions = True

    for block in _iter_blocks(doc):
        # ---------- TABLE ----------
        if isinstance(block, Table):
            if current_q is not None and current_key == "question":
                tbl_text = _table_to_text(block)
                if tbl_text:
                    current_q["question"] += tbl_text + "\n"
            continue

        raw = block.text.replace("\r", "")
        text = raw.strip()
        if not text:
            continue

        if text.startswith("###Section"):
            current_section = text.replace("###Section", "").strip()
            continue

        if text.startswith("#Hindi_directions"):
            process_questions = True
            continue

        if text.startswith("#English_directions"):
            process_questions = False
            continue

        if text.startswith("#Question"):
            if current_q and current_q.get("question", "").strip():
                parsed_questions.append(current_q)
            current_q = None
            if not process_questions:
                continue

            current_q = {
                "subject": current_section,
                "chapter": "Misc",
                "question": "",
                "options": [],
                "correct_index": 0,
                "explanation": ""
            }
            current_key = "question"
            q_text = re.sub(r"^#Question\s*\d*", "", text).strip()
            if q_text:
                current_q["question"] += q_text + "\n"
            continue

        if not current_q:
            continue

        # ---------- Section tags ----------
        if text.startswith("#Options"):
            current_key = "options"
            # "#Options ###A" ke baad same line me option ho to
            rest = re.sub(r"^#Options\s*(###[A-J])?", "", text).strip()
            if rest:
                current_q["options"].append(re.sub(r"^[A-J][\.\)]\s*", "", rest).strip())
            continue

        if text.startswith("#Correct_option"):
            current_key = "correct"
            rest = text.replace("#Correct_option", "").strip().upper()
            if rest[:1] in "ABCDEFGHIJ" and rest:
                current_q["correct_index"] = ord(rest[0]) - 65
            continue

        if text.startswith("#Solution"):
            current_key = "solution"
            continue

        if text.startswith("#tags"):
            current_key = "tags"
            continue

        # ---------- Content ----------
        if current_key == "options":
            if re.fullmatch(r"###[A-J]", text):
                continue
            text = re.sub(r"^###[A-J]\s*", "", text)
            opt_text = re.sub(r"^[A-J][\.\)]\s*", "", text).strip()
            if opt_text:
                current_q["options"].append(opt_text)

        elif current_key == "correct":
            letter = text.upper()
            if len(letter) == 1 and letter in "ABCDEFGHIJ":
                current_q["correct_index"] = ord(letter) - 65

        elif current_key == "solution":
            current_q["explanation"] += raw.strip() + "\n"

        elif current_key == "tags":
            current_q["chapter"] = text
            current_key = None

        elif current_key == "question":
            current_q["question"] += raw.strip() + "\n"

    if current_q and current_q.get("question", "").strip():
        parsed_questions.append(current_q)

    for q in parsed_questions:
        q["question"] = re.sub(r"\n{3,}", "\n\n", q["question"].strip())
        q["explanation"] = re.sub(r"\n{3,}", "\n\n", q["explanation"].strip())
        if q["options"]:
            q["correct_index"] = max(0, min(q["correct_index"], len(q["options"]) - 1))

    return parsed_questions


def validate_parsed(parsed_data):
    """Check karta hai ki question aur options sahi se aaye ya nahi"""
    valid = []
    errors = []
    for i, q in enumerate(parsed_data):
        if not q.get("question"):
            errors.append(f"Q{i+1}: question ka text missing hai.")
            continue
        if len(q.get("options", [])) < 2:
            errors.append(f"Q{i+1} '{q.get('question')[:20]}...' me 2 se kam options hain.")
            continue
        valid.append(q)
    return valid, errors
