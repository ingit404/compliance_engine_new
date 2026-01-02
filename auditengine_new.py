import os
import sys
import json
import pandas as pd
import fitz
from typing import List,Dict
from contextlib import contextmanager
from google import genai
from google.genai import types
from prompt import SYSTEM_PROMPT
from dotenv import load_dotenv

load_dotenv()

#the helper fucktions

def validate_document(pdf_path: str) -> None:
    doc = fitz.open(pdf_path)

    if len(doc) < 1:
        raise ValueError("Empty document")

    text = ""
    for page in doc[:9]:
        text += page.get_text()

    text = text.lower()

    required_keywords = ["loan", "interest", "borrower","PAN","AADHAAR","Customer Name",
        "tenure", "repayment", "lender", "apr",'penalty','gold loan',
        'loan id']

    matches = sum(1 for k in required_keywords if k in text)

    if matches < 3:
        raise ValueError("Not a loan document")


def build_final_prompt(user_instructions: str = "") -> str:
    """
    Safely appends optional user instructions to the base audit prompt.
    """
    if user_instructions:
        return (
            SYSTEM_PROMPT
            + "\n\n### ADDITIONAL USER INSTRUCTIONS\n"
            + user_instructions.strip()
        )
    return SYSTEM_PROMPT


#llm parser (helper funck)
def parse_model_output(response_text: str) -> List[Dict]:
    "clens llm output"
    clean = response_text.replace("```json", "").replace("```", "")
    clean=clean.strip().strip("'")
    return json.loads(clean)


def run_llm_audit(
        ground_truth: str,
        clm: str,
        GL_regulation: str,
        target_doc: str,
        user_prompt: str,
        output_excel_path: str
):

    #Validate document
    try:
        validate_document(target_doc)
    except ValueError as e:
        return [{
            "page_number": None,
            "word/phrase_highlighted": "",
            "whats_wrong": str(e),
            "priority": "p0"
        }]

    #Setup Gemini
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("API key missing")

    client = genai.Client(api_key=api_key)

    ground_truth_file = client.files.upload(file=ground_truth)
    clm_file = client.files.upload(file=clm)
    gl_file = client.files.upload(file=GL_regulation)
    target_file = client.files.upload(file=target_doc)

    model_2 = "gemini-3-flash-preview"
    model_3 = "gemini-3-pro-preview"

    final_prompt = build_final_prompt(user_prompt or "")

    #Model_2
    response_2 = client.models.generate_content(
        model=model_2,
        contents=[ground_truth_file, clm_file, gl_file, target_file, final_prompt],
        config=types.GenerateContentConfig(temperature=0.1)
    )
    data_2 = parse_model_output(response_2.text)

    #model_3
    response_3 = client.models.generate_content(
        model=model_3,
        contents=[ground_truth_file, clm_file, gl_file, target_file, final_prompt],
        config=types.GenerateContentConfig(temperature=0.1)
    )
    data_3 = parse_model_output(response_3.text)

    #Merge results
    def make_key(item):
        return (
            item.get("page_number"),
            item.get("word/phrase_highlighted", "").strip().lower(),
            item.get("whats_wrong", "").strip().lower(),
            item.get("priority", "").strip().lower()
        )

    merged = {}
    for item in data_2 + data_3:
        merged[make_key(item)] = item

    final_data = list(merged.values())
    df = pd.DataFrame(final_data)

    if "priority" not in df.columns:
        df["priority"] = "p0"

    df = df[["page_number", "word/phrase_highlighted", "whats_wrong", "priority"]]
    df.to_excel(output_excel_path, index=False)

    return final_data



#pdf highlighting logic


@contextmanager
def silence_mupdf():
    """
    Suppresses PyMuPDF stderr noise.
    """
    old_stderr = sys.stderr
    sys.stderr = open(os.devnull, "w")
    try:
        yield
    finally:
        sys.stderr.close()
        sys.stderr = old_stderr


def normalize_token(t):
    if not t:
        return ""
    return (
         t.replace("\n", " ")
         .replace("\r", " ")
         .replace("\u00ad", "")
         .replace("\xa0", " ")
         .replace("*", "")
         .replace(":", "")
         .replace("|", "")
         .replace("(", "")
         .replace(")", "")
         .replace("%", "")
         .replace(",", "")
         .lower()
         .strip()
    )


def find_phrase_rects_word_level(page, phrase: str):
    """
    Word-level fallback search for phrases not found by search_for.
    """
    words = page.get_text("words")
    if not words:
        return []

    phrase_tokens = [
        normalize_token(t)
        for t in phrase.split()
        if normalize_token(t)
    ]
    page_tokens = [normalize_token(w[4]) for w in words]
    rects = []
    window = len(phrase_tokens)

    for i in range(len(page_tokens)):
        chunk = page_tokens[i:i + window + 2]
        joined = " ".join(chunk)

        if all(p in joined for p in phrase_tokens):
            for j in range(i, min(i + window + 2, len(words))):
                rects.append(fitz.Rect(words[j][:4]))

    return rects
def highlight_pdf(
    pdf_path: str,
    output_path: str,
    data: List[Dict]
):
    """
    Highlights identified compliance issues in the PDF
    and writes an annotated output PDF.
    """

    with silence_mupdf():
        doc = fitz.open(pdf_path)

        for item in data:
            try:
                page_no = int(item["page_number"]) - 1
                phrase = (item.get("word/phrase_highlighted") or "").strip()
                note = item.get("whats_wrong", "").strip()
                priority = item.get("priority","").strip()
            except Exception:
                continue

            if not phrase or page_no < 0 or page_no >= len(doc):
                continue

            page = doc[page_no]

            flags = 0
            if hasattr(fitz, "TEXT_IGNORECASE"):
                flags |= fitz.TEXT_IGNORECASE
            if hasattr(fitz, "TEXT_DEHYPHENATE"):
                flags |= fitz.TEXT_DEHYPHENATE

            rects = page.search_for(phrase, flags=flags)

            if not rects:
                rects = find_phrase_rects_word_level(page, phrase)

            for rect in rects:
                annot = page.add_highlight_annot(rect)
                if note:
                     priority = item.get("priority","p0") 
                     annot.set_info(
                        title=f"⚠️ PRIORITY: {priority.upper()}",
                        subject=f"Priority:{priority}",
                        content=f"COMPLIANCE OBSERVATION: {note}"
                    )
                annot.update(opacity=0.4)

        doc.save(
            output_path,
            garbage=4,
            deflate=True,
            clean=True
        )
        doc.close()
