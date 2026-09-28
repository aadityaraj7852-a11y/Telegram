"""
utils/docx_parser.py
MockRise Word (.docx) parser.

Supports:
- #Question / #Options / #Correct_option / #Solution / #tags
- Hindi/English directions
- Multi-line questions (Kathan-I/II etc.)
- Tables placed immediately below a question (Match the following)
- Paragraph + table body order
"""
import re
from docx import Document
from docx.text.paragraph import Paragraph
from docx.table import Table


def _iter_blocks(doc):
    """Document ke paragraphs aur tables ko original body order me return karo."""
    for child in doc.element.body.iterchildren():
        tag = child.tag.split('}')[-1]
        if tag == 'p':
            yield Paragraph(child, doc)
        elif tag == 'tbl':
            yield Table(child, doc)


def _table_to_text(tbl):
    """Table ko readable plain text me convert karo."""
    lines = []
    for row in tbl.rows:
        cells = []
        for cell in row.cells:
            value = cell.text.replace('\r', '').strip()
            # Merged cells python-docx me duplicate ho sakte hain.
            if value and (not cells or cells[-1] != value):
                cells.append(value)
        if cells:
            lines.append("   ➜   ".join(cells))
    return "\n".join(lines)


def _clean_question_text(text):
    text = text.replace('\r', '')
    # 3+ blank lines ko 2 lines tak limit karo, lekin real line breaks preserve karo.
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _clean_option(text):
    text = text.strip()
    text = re.sub(r'^###[A-J]\s*', '', text, flags=re.I)
    text = re.sub(r'^[A-J][\.\)]\s*', '', text, flags=re.I)
    return text.strip()


def parse_docx(file_path):
    """MockRise DOCX ko questions list me parse karta hai."""
    doc = Document(file_path)
    questions = []
    current = None
    section = "General"
    field = None
    process_questions = True

    def flush():
        nonlocal current
        if not current:
            return

        current["question"] = _clean_question_text(current.get("question", ""))
        current["explanation"] = _clean_question_text(current.get("explanation", ""))

        if not current["question"]:
            current = None
            return

        opts = current.get("options", [])
        letter = str(current.pop("correct_letter", "A")).strip().upper()
        m = re.search(r'[A-J]', letter)
        letter = m.group(0) if m else 'A'
        current["correct_index"] = max(0, min(ord(letter) - 65, len(opts) - 1)) if opts else 0
        current["subject"] = current.pop("section", section) or "General"
        current.setdefault("chapter", "Misc")
        questions.append(current)
        current = None

    for block in _iter_blocks(doc):
        # ---------------- TABLE ----------------
        if isinstance(block, Table):
            if current is not None and field == "question" and process_questions:
                table_text = _table_to_text(block)
                if table_text:
                    if current["question"] and not current["question"].endswith('\n'):
                        current["question"] += '\n'
                    current["question"] += table_text + '\n'
            continue

        text = block.text.replace('\r', '')
        stripped = text.strip()

        # Empty paragraph: question ke andar ho to line-break preserve karo.
        if not stripped:
            if current is not None and field == "question" and process_questions:
                current["question"] += '\n'
            continue

        # ---------------- SECTION / DIRECTIONS ----------------
        if stripped.startswith("###Section"):
            section = stripped.replace("###Section", "", 1).strip() or "General"
            continue

        if stripped.startswith("#Hindi_directions"):
            process_questions = True
            continue

        if stripped.startswith("#English_directions"):
            process_questions = False
            # English section me chal raha question ho to save/clear karo.
            if current is not None:
                flush()
            field = None
            continue

        # ---------------- QUESTION ----------------
        if re.match(r'^#Question\s*\d*', stripped, re.I):
            if not process_questions:
                current = None
                field = None
                continue

            flush()
            current = {
                "subject": section,
                "chapter": "Misc",
                "question": "",
                "options": [],
                "correct_index": 0,
                "explanation": "",
                "section": section,
            }
            field = "question"

            q_text = re.sub(r'^#Question\s*\d*\s*', '', text, flags=re.I).strip()
            if q_text:
                current["question"] = q_text + '\n'
            continue

        if current is None:
            continue

        # ---------------- FIELD SWITCHES ----------------
        if stripped.startswith("#Options"):
            field = "options"
            continue

        if stripped.startswith("#Correct_option"):
            field = "correct"
            continue

        if stripped.startswith("#Solution"):
            field = "explanation"
            continue

        if stripped.startswith("#tags"):
            field = "tags"
            continue

        # ---------------- FIELD CONTENT ----------------
        if field == "question":
            # Kisi accidental field tag ko question me nahi daalna.
            if stripped.startswith('#'):
                continue
            current["question"] += text + '\n'

        elif field == "options":
            # ###A / ###B headings skip karo.
            if re.fullmatch(r'###[A-J]', stripped, re.I):
                continue
            option = _clean_option(stripped)
            if option:
                current["options"].append(option)

        elif field == "correct":
            if stripped:
                current["correct_letter"] = stripped

        elif field == "explanation":
            current["explanation"] += text + '\n'

        elif field == "tags":
            if stripped:
                # Existing importer chapter field ke liye first tag use karo.
                current["chapter"] = stripped

    flush()
    return questions


def validate_parsed(parsed_data):
    """Question aur options minimum validation."""
    valid = []
    errors = []
    for i, q in enumerate(parsed_data):
        question = q.get("question", "").strip()
        options = q.get("options", [])
        if not question:
            errors.append(f"Question {i + 1}: question text missing hai.")
            continue
        if len(options) < 2:
            errors.append(f"Question '{question[:30]}...' me 2 se kam options hain.")
            continue
        valid.append(q)
    return valid, errors


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("Usage: python utils/docx_parser.py <file.docx>")
        raise SystemExit(1)

    qs = parse_docx(sys.argv[1])
    print(len(qs), "questions")
    print(json.dumps(qs[:3], ensure_ascii=False, indent=2))
