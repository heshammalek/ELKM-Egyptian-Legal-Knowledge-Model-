
"""
scripts/grammar.py
ELKM - استخراج المواد من النص القانوني العربي
"""

import re
from pathlib import Path


def clean_text(text: str) -> str:
    """
    ينظف النص من تنسيق Markdown
    - يزيل ** و __
    - يزيل ### و ## و #
    - يزيل --- و ___
    - يزيل الهاشات والنجوم الزائدة
    """
    # إزالة تنسيق Markdown
    text = re.sub(r"\*\*", "", text)           # إزالة **
    text = re.sub(r"__", "", text)             # إزالة __
    text = re.sub(r"###?\s*", "", text)        # إزالة ### و ## و #
    text = re.sub(r"---+\s*", "", text)        # إزالة ---
    text = re.sub(r"___+\s*", "", text)        # إزالة ___
    # تنظيف المسافات الزائدة
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def parse_legal_text(text: str) -> dict:
    """
    يستخرج المواد والأبواب والفصول من النص القانوني
    """
    
    # تنظيف النص من التنسيق أولاً
    text = clean_text(text)
    
    result = {
        "preamble": [],
        "chapters": [],
        "sections": [],
        "articles": [],
        "statistics": {
            "total_articles": 0,
            "total_chapters": 0,
            "total_sections": 0,
            "preamble_lines": 0
        }
    }

    # ── استخراج الأبواب ──────────────────────────────────
    chapters = []
    for ch in re.finditer(r"الباب\s+([^\n]+)", text):
        chapters.append({
            "type": "chapter",
            "title": ch.group(1).strip(),
            "position": ch.start(),
            "end": 0
        })
    for i, ch in enumerate(chapters):
        ch["end"] = chapters[i + 1]["position"] if i + 1 < len(chapters) else len(text)
    result["chapters"] = chapters
    result["statistics"]["total_chapters"] = len(chapters)

    # ── استخراج الفصول ──────────────────────────────────
    sections = []
    for sec in re.finditer(r"الفصل\s+([^\n]+)", text):
        sections.append({
            "type": "section",
            "title": sec.group(1).strip(),
            "position": sec.start(),
            "end": 0
        })
    for i, sec in enumerate(sections):
        sec["end"] = sections[i + 1]["position"] if i + 1 < len(sections) else len(text)
    result["sections"] = sections
    result["statistics"]["total_sections"] = len(sections)

    # ── استخراج المواد ──────────────────────────────────
    # بعد التنظيف، النمط بقى بسيط: "مادة (١)" أو "مادة ١"
    pattern = r"ماده?\s*\(?\s*([٠-٩\d]+)\s*\)?\s*[:.-]?\s*\n?"
    matches = list(re.finditer(pattern, text))
    
    arabic_map = {'٠':'0','١':'1','٢':'2','٣':'3','٤':'4',
                  '٥':'5','٦':'6','٧':'7','٨':'8','٩':'9'}
    
    temp = []
    seen = set()
    
    for i, m in enumerate(matches):
        num_str = m.group(1)
        for a, b in arabic_map.items():
            num_str = num_str.replace(a, b)
        try:
            num = int(num_str)
        except:
            continue
        
        # فلترة
        if num == 247:
            continue
        if num < 1 or num > 246:
            continue
        if num in seen:
            continue
        seen.add(num)
        
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        
        # ربط بالباب والفصل
        chapter_title = None
        for ch in chapters:
            if ch["position"] <= start < ch["end"]:
                chapter_title = ch["title"]
                break
        section_title = None
        for sec in sections:
            if sec["position"] <= start < sec["end"]:
                section_title = sec["title"]
                break
        
        temp.append({
            "article_number": num,
            "text": text[start:end].strip(),
            "chapter": chapter_title,
            "section": section_title
        })
    
    temp = sorted(temp, key=lambda x: x["article_number"])
    result["articles"] = temp
    result["statistics"]["total_articles"] = len(temp)

    return result


if __name__ == "__main__":
    test_file = Path(__file__).parent.parent / "corpus" / "normalized" / "EG-CONST-2014_normalized.txt"
    if test_file.exists():
        with open(test_file, encoding="utf-8") as f:
            text = f.read()
        result = parse_legal_text(text)
        print("=" * 50)
        print(f"المواد: {result['statistics']['total_articles']}")
        print(f"الأبواب: {result['statistics']['total_chapters']}")
        print(f"الفصول: {result['statistics']['total_sections']}")
        print("=" * 50)
        if result["articles"]:
            print("\nأول 5 مواد:")
            for art in result["articles"][:5]:
                print(f"  مادة {art['article_number']}: {art['text'][:60]}...")
            print(f"\nآخر 5 مواد:")
            for art in result["articles"][-5:]:
                print(f"  مادة {art['article_number']}: {art['text'][:60]}...")
    else:
        print("❌ ملف النص غير موجود")
