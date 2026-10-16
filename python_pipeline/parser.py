import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Union

SECTION_HEADERS = [
    "summary",
    "objective",
    "experience",
    "professional experience",
    "work experience",
    "education",
    "skills",
    "technical skills",
    "certifications",
    "projects",
    "training",
    "awards",
]


def normalize_text(text: str) -> str:
    """Normalize whitespace and common resume separators."""
    normalized = re.sub(r"\r\n|\r", "\n", text)
    normalized = re.sub(r"\t", " ", normalized)
    normalized = re.sub(r" {2,}", " ", normalized)
    return normalized.strip()


def read_resume_text(resume_path: Union[str, Path]) -> str:
    """Read resume content from a text file or PDF."""
    path = Path(resume_path)
    if not path.exists():
        raise FileNotFoundError(f"Resume file not found: {path}")

    if path.suffix.lower() == ".pdf":
        try:
            from pdfminer.high_level import extract_text
        except Exception as exc:  # pragma: no cover - depends on optional dependency
            raise RuntimeError("PDF resume parsing requires pdfminer.six.") from exc

        text = extract_text(str(path))
        if not text:
            raise ValueError(f"No text could be extracted from PDF: {path}")
        return normalize_text(text)

    return normalize_text(path.read_text(encoding="utf-8", errors="ignore"))


def extract_resume_sections(resume_text: str) -> Dict[str, str]:
    """Extracts resume sections based on common headings."""
    text = normalize_text(resume_text)
    pattern = re.compile(
        r"^({})(?:\s*[:\-]?\s*)$".format("|".join(re.escape(h) for h in SECTION_HEADERS)),
        flags=re.IGNORECASE | re.MULTILINE,
    )

    matches = list(pattern.finditer(text))
    if not matches:
        return {"full_text": text}

    sections = {}
    for index, match in enumerate(matches):
        header = match.group(1).strip().lower()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        section_text = text[start:end].strip()
        sections[header] = section_text

    if "full_text" not in sections:
        sections["full_text"] = text

    return sections


def _split_list_items(section_text: str) -> List[str]:
    if not section_text:
        return []
    parts = re.split(r"[\/,]\\s*", section_text)
    return [p.strip() for p in parts if p.strip()]


import re
from typing import List

def extract_job_titles(resume_text: str) -> List[str]:
    text = normalize_text(resume_text)
    sections = extract_resume_sections(text)
    
    # 1. Broad section fallbacks for work experience
    exp_keys = [
        "work experience", "professional experience", "experience",
        "employment history", "work history", "career history",
        "relevant experience", "professional background"
    ]
    
    experience_text = ""
    for key in exp_keys:
        if sections.get(key):
            experience_text = sections[key]
            break
            
    if not experience_text:
        experience_text = text

    lines = [line.strip() for line in experience_text.splitlines() if line.strip()]

    # 2. Comprehensive Title & Seniority Regex
    levels = r"(?:senior|sr\.?|junior|jr\.?|lead|principal|chief|head|vp|vice president|director|manager|staff|associate|assistant|intern|co-?founder|founder|executive)"
    roles = r"(?:developer|engineer|analyst|manager|director|consultant|architect|specialist|support|lead|designer|administrator|coordinator|scientist|product|officer|strategist|executive|representative|recruiter|accountant|auditor|marketer|writer|editor|technician|operator|advocate|agent|generalist|advisor|counsel|researcher|practitioner|programmer|tester|owner|partner)"
    
    title_pattern = re.compile(f"\\b(?:{levels}|{roles})\\b", flags=re.IGNORECASE)

    # 3. Action verbs that indicate a bullet point rather than a job title header
    action_verb_pattern = re.compile(
        r"^(?:managed|developed|engineered|designed|led|created|implemented|built|spearheaded|assisted|provided|handled|maintained|analyzed|collaborated|responsible for|worked|optimized)\b",
        flags=re.IGNORECASE
    )

    titles = []
    for line in lines:
        # Strip leading bullet points, numbers, and symbols
        clean_line = re.sub(r"^[\s•\*\-\d\.\)\(\>]+", "", line).strip()
        
        # Skip if the line starts with a bullet point action verb
        if action_verb_pattern.search(clean_line):
            continue

        if title_pattern.search(clean_line):
            # Clean off company separators like '|'
            candidate = re.sub(r"\s*\|.*$", "", clean_line)
            
            # Split at 'at', '@', dates, or spaced dashes (preserves hyphenated words like "Full-Stack")
            candidate = re.split(
                r"\s+(?:@|\bat\b|\b(?:present|current|\d{4})\b|[-–—]\s+)", 
                candidate, 
                1, 
                flags=re.IGNORECASE
            )[0]
            
            # Clean up trailing punctuation
            candidate = re.sub(r"[,–—\-\(\)]\s*$", "", candidate).strip()

            # Validate word length (1 to 7 words)
            words = candidate.split()
            if candidate and 1 <= len(words) <= 7:
                # Ensure the extracted phrase still contains a core job title keyword
                if title_pattern.search(candidate):
                    titles.append(candidate)

    # Deduplicate while preserving original order
    return list(dict.fromkeys(titles))


def extract_education(resume_text: str) -> List[str]:
    text = normalize_text(resume_text)
    sections = extract_resume_sections(text)
    education_text = sections.get("education", "").strip()

    # Fallback: Search whole text if education section extraction yields nothing
    if not education_text:
        education_text = text

    # 1. Degrees & Qualifications (Full names and common variants)
    degrees = r"\b(?:bachelor|bachelors|master|masters|associate|associates|doctorate|doctor|phd|ph\.d|mba|md|jd|diploma|certificate)\b"
    
    # 2. Degree Abbreviation Patterns (e.g., B.S., BS, M.S., B.Tech, B.E., B.A., M.B.A.)
    abbreviations = r"\b(?:b\.?s\.?c?|m\.?s\.?c?|b\.?a\.?|m\.?a\.?|b\.?tech|m\.?tech|b\.?e\.?|m\.?e\.?|b\.?b\.?a\.?|m\.?b\.?a\.?|b\.?com|m\.?com|ll\.?b|ll\.?m)\b"
    
    # 3. Institution Keywords
    institutions = r"\b(?:university|college|institute|polytechnic|academy|school of)\b"
    
    # 4. Academic Markers & Honors
    academic_keywords = r"\b(?:gpa|cum laude|magna cum laude|summa cum laude|dean'?s list|major|minor|graduated|graduation|thesis|coursework)\b"

    combined_pattern = re.compile(
        f"{degrees}|{abbreviations}|{institutions}|{academic_keywords}",
        flags=re.IGNORECASE,
    )

    lines = [line.strip() for line in education_text.splitlines() if line.strip()]
    
    education_entries = []
    current_block = []

    for line in lines:
        is_match = bool(combined_pattern.search(line))
        
        # Check if line contains supporting education details (e.g., dates/years, GPA, location)
        is_metadata = bool(re.search(r"\b(?:\d{4}|present|gpa|cum laude|honors)\b", line, re.IGNORECASE))

        if is_match:
            current_block.append(line)
        elif current_block and is_metadata:
            # Append trailing date/GPA lines to the current education block
            current_block.append(line)
        else:
            if current_block:
                education_entries.append(" — ".join(current_block))
                current_block = []

    # Flush remaining block
    if current_block:
        education_entries.append(" — ".join(current_block))

    # Deduplicate while preserving original order
    return list(dict.fromkeys(education_entries))

def extract_experience_years(resume_text: str) -> int | None:
    text = normalize_text(resume_text).lower()
    year_range = re.search(r"(\d+)\s*[-+]\s*year", text)
    if year_range:
        return int(year_range.group(1))

    range_pattern = re.compile(
        r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)?\s*(\d{4})\s*[-–—]\s*(?:present|current|(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)?\s*(\d{4}))",
        flags=re.IGNORECASE,
    )
    total_years = 0
    for match in range_pattern.finditer(text):
        start_year = int(match.group(1))
        end_year = datetime.now().year if match.group(2) is None or match.group(2).lower() in {"present", "current"} else int(match.group(2))
        total_years += max(0, end_year - start_year)

    return total_years or None


def extract_audience_profile(resume_text: str) -> Dict[str, object]:
    return {
        "job_titles": extract_job_titles(resume_text),
        "education": extract_education(resume_text),
        "experience_years": extract_experience_years(resume_text),
        "audience_terms": [
            *extract_job_titles(resume_text),
            *extract_education(resume_text),
        ],
    }
