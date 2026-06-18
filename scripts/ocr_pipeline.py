"""
================================================================================
ELKM - OCR Pipeline
scripts/ocr_pipeline.py

المحرك: Gemini API (نظيف ودقيق)
المحركات المعلّقة: EasyOCR, Google Document AI

الاستخدام:
  python -m scripts.ocr_pipeline --file "دستور_جمهورية_مصر_العربية_المعدل_لسنة_2014.pdf"
================================================================================
"""

import os
import re
import json
import time
import argparse
from pathlib import Path
from datetime import datetime
from typing import Tuple, Dict, Any

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


# ════════════════════════════════════════════════════════
# 1. إعداد البيئة
# ════════════════════════════════════════════════════════

def load_env(env_path: str = ".env") -> dict:
    env = {}
    env_file = Path(env_path)
    if not env_file.exists():
        raise FileNotFoundError(f"ملف .env غير موجود في: {env_file.absolute()}")
    with open(env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                value = value.strip().strip('"').strip("'")
                env[key.strip()] = value
    return env


ENV = load_env(".env")
GEMINI_API_KEY = ENV.get("GEMINI_API_KEY", "")

BASE_DIR = Path(__file__).parent.parent
RAW_DIR = BASE_DIR / "corpus" / "raw"
NORMALIZED_DIR = BASE_DIR / "corpus" / "normalized"
RAW_DIR.mkdir(parents=True, exist_ok=True)
NORMALIZED_DIR.mkdir(parents=True, exist_ok=True)


# ════════════════════════════════════════════════════════
# 2. خريطة الملفات
# ════════════════════════════════════════════════════════

FILE_REGISTRY = {
    "constitution_2014.pdf":
        ("EG-CONST-2014", "constitution"),
    "دستور_جمهورية_مصر_العربية_المعدل_لسنة_2014.pdf":
        ("EG-CONST-2014", "constitution"),
    "labor_law_12_2003.pdf":
        ("EG-LAW-2003-012", "law"),
    "civil_code.pdf":
        ("EG-LAW-1948-131", "law"),
    "penal_code.pdf":
        ("EG-LAW-1937-058", "law"),
    "criminal_procedure.pdf":
        ("EG-LAW-1950-150", "law"),
    "state_council_law.pdf":
        ("EG-LAW-1972-047", "law"),
}


# ════════════════════════════════════════════════════════
# 3. استخراج النص من Gemini
# ════════════════════════════════════════════════════════

def process_with_gemini(pdf_path: Path) -> Tuple[str, int]:
    """يستخرج النص من PDF باستخدام Gemini API"""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise ImportError("pip install google-genai")

    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY غير موجود في .env")

    client = genai.Client(api_key=GEMINI_API_KEY)

    print(f"  ↑ رفع الملف لـ Gemini... ({pdf_path.stat().st_size // 1024} KB)")

    with open(pdf_path, "rb") as f:
        uploaded = client.files.upload(
            file=f,
            config=types.UploadFileConfig(
                mime_type="application/pdf",
                display_name=pdf_path.name
            )
        )

    while uploaded.state.name == "PROCESSING":
        time.sleep(2)
        uploaded = client.files.get(name=uploaded.name)

    print("  ↳ استخراج النص...")

    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=[
            types.Part.from_uri(
                file_uri=uploaded.uri,
                mime_type="application/pdf"
            ),
            """استخرج النص الكامل من هذا المستند القانوني المصري.
قواعد صارمة:
- استخرج النص كما هو بدون أي تعديل أو تلخيص
- احتفظ بأرقام المواد وعناوين الأبواب والفصول كما هي
- لا تضف أي نص من عندك
- النص فقط"""
        ],
        config=types.GenerateContentConfig(temperature=0)
    )

    client.files.delete(name=uploaded.name)

    text = response.text.strip()
    
    try:
        import fitz
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
    except:
        total_pages = max(1, pdf_path.stat().st_size // 50_000)

    print(f"  ✓ {total_pages} صفحة | {len(text):,} حرف")
    return text, total_pages


# ════════════════════════════════════════════════════════
# 4. استخراج المواد (Grammar)
# ════════════════════════════════════════════════════════

def parse_legal_text(text: str) -> Dict[str, Any]:
    """يستخرج المواد والأبواب والفصول من النص القانوني"""
    from scripts.grammar import parse_legal_text as grammar_parse
    return grammar_parse(text)


# ════════════════════════════════════════════════════════
# 5. تطبيع النص
# ════════════════════════════════════════════════════════

def normalize_arabic(text: str) -> str:
    text = re.sub(r"[إأآ]", "ا", text)
    text = re.sub(r"ى", "ي", text)
    text = re.sub(r"ة", "ه", text)
    text = re.sub(r"[\u064B-\u065F\u0670]", "", text)
    text = re.sub(r"ـ+", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ════════════════════════════════════════════════════════
# 6. بناء المستند
# ════════════════════════════════════════════════════════

def build_document(
    pdf_path: Path,
    law_id: str,
    law_type: str,
    full_text: str,
    total_pages: int,
    engine: str
) -> Dict[str, Any]:
    """يبني المستند النهائي"""
    parsed = parse_legal_text(full_text)
    
    return {
        "doc_id": law_id,
        "doc_type": law_type,
        "ocr_engine": engine,
        "source_file": pdf_path.name,
        "processed_at": datetime.now().isoformat(),
        "total_pages": total_pages,
        "total_chars": len(full_text),
        "total_articles": parsed["statistics"]["total_articles"],
        "full_text_display": full_text,
        "full_text_normalized": normalize_arabic(full_text),
        "structure": {
            "chapters": parsed["chapters"],
            "sections": parsed["sections"]
        },
        "articles": parsed["articles"],
        "grammar_stats": parsed["statistics"]
    }


# ════════════════════════════════════════════════════════
# 7. حفظ النتيجة
# ════════════════════════════════════════════════════════

def save_document(doc: Dict[str, Any]):
    doc_id = doc["doc_id"]
    json_path = NORMALIZED_DIR / f"{doc_id}.json"
    txt_path = NORMALIZED_DIR / f"{doc_id}_normalized.txt"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(doc["full_text_normalized"])

    print(f"  ✅ {json_path.relative_to(BASE_DIR)}")
    print(f"  ✅ {txt_path.relative_to(BASE_DIR)}")
    print(f"  📊 مواد: {doc['total_articles']}")
    print(f"  📊 أبواب: {len(doc['structure']['chapters'])}")
    print(f"  📊 فصول: {len(doc['structure']['sections'])}")


# ════════════════════════════════════════════════════════
# 8. المعالجة الرئيسية
# ════════════════════════════════════════════════════════

def process_file(filename: str, engine: str = "gemini", dry_run: bool = False):
    pdf_path = RAW_DIR / filename

    if not pdf_path.exists():
        print(f"✗ الملف غير موجود: {pdf_path.absolute()}")
        return

    if filename not in FILE_REGISTRY:
        print(f"⚠ '{filename}' غير مسجّل في FILE_REGISTRY")
        return

    law_id, law_type = FILE_REGISTRY[filename]

    print(f"\n{'='*52}")
    print(f"  📄 الملف   : {filename}")
    print(f"  🆔 المعرّف : {law_id}")
    print(f"  📂 النوع   : {law_type}")
    print(f"  ⚙️ المحرك  : {engine}")
    print(f"{'='*52}\n")

    if dry_run:
        print("  [DRY RUN] لا يُرسل طلب للـ API")
        return

    text, pages = process_with_gemini(pdf_path)
    doc = build_document(pdf_path, law_id, law_type, text, pages, engine)
    save_document(doc)
    print(f"\n✅ {law_id} — اكتمل بنجاح\n")


def process_all(engine: str = "gemini", dry_run: bool = False):
    pdfs = list(RAW_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"لا توجد ملفات PDF في {RAW_DIR}")
        return
    print(f"وجدت {len(pdfs)} ملف PDF")
    for p in pdfs:
        process_file(p.name, engine=engine, dry_run=dry_run)


# ════════════════════════════════════════════════════════
# 9. CLI
# ════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ELKM OCR Pipeline - Gemini")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", "-f", help="اسم ملف PDF في corpus/raw/")
    group.add_argument("--all", "-a", action="store_true",
                       help="معالجة كل ملفات raw/")

    parser.add_argument("--dry-run", action="store_true",
                        help="اختبار بدون إرسال للـ API")

    args = parser.parse_args()

    print("─" * 45)
    print(f"المحرك : Gemini")
    print(f"API Key: {'✓ موجود' if GEMINI_API_KEY else '❌ غير محدد'}")
    print("─" * 45)

    if args.file:
        process_file(args.file, dry_run=args.dry_run)
    else:
        process_all(dry_run=args.dry_run)


# ════════════════════════════════════════════════════════
# 10. المحركات المعلّقة (كومنتات)
# ════════════════════════════════════════════════════════

'''
المحرك المعلّق: EasyOCR
----------------------------
import easyocr

def ocr_with_easyocr(pdf_path: Path) -> str:
    reader = easyocr.Reader(['ar'], gpu=False)
    doc = fitz.open(pdf_path)
    full_text = []
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=150)
        img_path = f"temp_page_{i}.png"
        pix.save(img_path)
        result = reader.readtext(img_path, detail=0, paragraph=True)
        full_text.append("\n".join(result))
    return "\n\n".join(full_text)

المحرك المعلّق: Google Document AI
----------------------------
from google.cloud import documentai

def process_with_document_ai(pdf_path: Path) -> Tuple[str, int]:
    client = documentai.DocumentProcessorServiceClient()
    result = client.process_document(...)
    return result.document.text, len(result.document.pages)
'''
