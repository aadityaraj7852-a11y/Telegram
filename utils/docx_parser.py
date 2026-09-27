"""
utils/docx_parser.py
Word (.docx) files ko parse karne ka logic.
Ye file sirf #Hindi_directions wale questions ko extract karegi aur #English_directions walo ko ignore karegi.
"""
import docx
import re

def parse_docx(file_path):
    doc = docx.Document(file_path)
    parsed_questions = []
    
    current_q = None
    current_section = "General"
    current_key = None
    
    # Naya Flag: Default true rakha hai, par tag ke hisaab se change hoga
    process_questions = True 
    
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
            
        # Section tag read karna
        if text.startswith("###Section"):
            current_section = text.replace("###Section", "").strip()
            continue
            
        # Direction check karna - yahan se decide hoga question lena hai ya nahi
        if text.startswith("#Hindi_directions"):
            process_questions = True
            continue
            
        if text.startswith("#English_directions"):
            process_questions = False
            continue
            
        # Question tag milne par naya question start karna
        if text.startswith("#Question"):
            # Agar English direction chal raha hai, to is question ko poori tarah skip kar do
            if not process_questions:
                current_q = None # Reset kar diya taaki iske options/answers bhi skip ho jayein
                continue

            # Agar pehle se koi Hindi question memory me hai, to use list me save kar do
            if current_q and current_q.get("question"):
                parsed_questions.append(current_q)
                
            current_q = {
                "subject": current_section,
                "chapter": "Misc",
                "question": "",
                "options": [],
                "correct_index": 0,
                "explanation": ""
            }
            current_key = "question"
            
            # "#Question 1" jaise tags ko hata kar main sawal nikalna
            q_text = re.sub(r"^#Question\s*\d*", "", text).strip()
            if q_text:
                current_q["question"] += q_text + "\n"
            continue
            
        # Agar current_q None hai (yani English question chal raha tha), to aage ki lines ignore karo
        if not current_q:
            continue
            
        # Options tag aane par
        if text.startswith("#Options"):
            current_key = "options"
            continue
            
        if current_key == "options":
            # Sub-tags jaise ###A, ###B ko ignore karna
            if text.startswith("###A") or text.startswith("###B") or text.startswith("###C") or text.startswith("###D"):
                continue
            # Agar option list ke baad Correct option aa jaye
            if text.startswith("#Correct_option"):
                current_key = "correct"
                continue
                
            # Option ke aage se "A. " ya "B. " hata kar option ko save karna
            opt_text = re.sub(r"^[A-D]\.\s*", "", text).strip()
            if opt_text:
                current_q["options"].append(opt_text)
            continue
            
        # Sahi answer tag
        if text.startswith("#Correct_option"):
            current_key = "correct"
            continue
            
        if current_key == "correct":
            if text.startswith("#Solution"):
                current_key = "solution"
                continue
            
            ans_letter = text.strip().upper()
            if ans_letter in ['A', 'B', 'C', 'D']:
                current_q["correct_index"] = ord(ans_letter) - ord('A')
            continue
            
        # Solution (Explanation) tag
        if text.startswith("#Solution"):
            current_key = "solution"
            continue
            
        if current_key == "solution":
            if text.startswith("#tags"):
                current_key = "tags"
                continue
            current_q["explanation"] += text + "\n"
            continue
            
        # Extra Tags (jaise Rajasthan GK)
        if text.startswith("#tags"):
            current_key = "tags"
            continue
            
        if current_key == "tags":
            current_q["chapter"] = text.strip()
            current_key = None
            continue
            
        # Bacha hua normal text (agar paragraph bada ho to)
        if current_key == "question":
            current_q["question"] += text + "\n"
        elif current_key == "solution":
            current_q["explanation"] += text + "\n"
            
    # File ke aakhri question ko list me save karna
    if current_q and current_q.get("question"):
        parsed_questions.append(current_q)
        
    # Extra spaces (newlines) saaf karna
    for q in parsed_questions:
        q["question"] = q["question"].strip()
        q["explanation"] = q["explanation"].strip()
        
    return parsed_questions

def validate_parsed(parsed_data):
    """Check karta hai ki question aur options sahi se aaye ya nahi"""
    valid = []
    errors = []
    for i, q in enumerate(parsed_data):
        if not q.get("question"):
            errors.append(f"Ek question ka text missing hai.")
            continue
        if len(q.get("options", [])) < 2:
            errors.append(f"Question '{q.get('question')[:20]}...' me 2 se kam options hain.")
            continue
        valid.append(q)
    return valid, errors
