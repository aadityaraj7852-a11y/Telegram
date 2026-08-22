"""
docx_parser.py
Word file se questions padhne ka logic.

Expected format in .docx file (ek simple, sikhane-jaisa format):

Subject: Physics
Chapter: Motion

Q1. Speed ka SI unit kya hai?
A) Kg
B) m/s
C) Newton
D) Watt
Answer: B
Explanation: Speed = distance/time, unit m/s hota hai.

Q2. ...
A) ...
B) ...
C) ...
D) ...
Answer: A

(Explanation optional hai)
Multiple chapters/subjects same file me ho sakte hain, bas naya
"Subject:" ya "Chapter:" line likhna hoga jahan se badle.
"""

import re
from docx import Document


def parse_docx(file_path):
    """
    Returns: list of dicts:
    {subject, chapter, question, options[4], correct_index, explanation}
    """
    doc = Document(file_path)
    lines = [p.text.strip() for p in doc.paragraphs if p.text.strip() != ""]

    results = []
    current_subject = "General"
    current_chapter = "General"

    q_text = None
    options = []
    correct_index = None
    explanation = ""

    def flush():
        nonlocal q_text, options, correct_index, explanation
        if q_text and len(options) >= 2 and correct_index is not None:
            results.append({
                "subject": current_subject,
                "chapter": current_chapter,
                "question": q_text,
                "options": options[:4] if len(options) >= 4 else options,
                "correct_index": correct_index,
                "explanation": explanation
            })
        q_text = None
        options = []
        correct_index = None
        explanation = ""

    for line in lines:
        subj_match = re.match(r"^subject\s*[:\-]\s*(.+)$", line, re.IGNORECASE)
        chap_match = re.match(r"^chapter\s*[:\-]\s*(.+)$", line, re.IGNORECASE)
        q_match = re.match(r"^q\d*[\.\)]\s*(.+)$", line, re.IGNORECASE)
        opt_match = re.match(r"^([A-Da-d])[\.\)]\s*(.+)$", line)
        ans_match = re.match(r"^answer\s*[:\-]\s*([A-Da-d])\s*$", line, re.IGNORECASE)
        exp_match = re.match(r"^explanation\s*[:\-]\s*(.+)$", line, re.IGNORECASE)

        if subj_match:
            flush()
            current_subject = subj_match.group(1).strip()
            continue
        if chap_match:
            flush()
            current_chapter = chap_match.group(1).strip()
            continue
        if q_match:
            flush()
            q_text = q_match.group(1).strip()
            continue
        if opt_match:
            options.append(opt_match.group(2).strip())
            continue
        if ans_match:
            letter = ans_match.group(1).upper()
            correct_index = ord(letter) - ord('A')
            continue
        if exp_match:
            explanation = exp_match.group(1).strip()
            continue

    flush()
    return results


def validate_parsed(parsed_questions):
    """Basic validation, returns (valid_list, error_list)"""
    valid = []
    errors = []
    for i, q in enumerate(parsed_questions, 1):
        if len(q["options"]) < 2:
            errors.append(f"Q{i}: kam se kam 2 options chahiye")
            continue
        if q["correct_index"] is None or q["correct_index"] >= len(q["options"]):
            errors.append(f"Q{i}: sahi 'Answer:' letter set nahi hai ya options se match nahi karta")
            continue
        if len(q["question"]) < 3:
            errors.append(f"Q{i}: question text bahut chota/khali hai")
            continue
        valid.append(q)
    return valid, errors
