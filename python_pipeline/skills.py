import re
from typing import Iterable, List, Optional

from .parser import extract_resume_sections, normalize_text


def default_skill_keywords() -> List[str]:
    return [
        # Programming & Languages
        "python",
        "r",
        "sas",
        "sql",
        "java",
        "javascript",
        "react",
        # SAS Specific
        "advanced analytics professional using sas 9",
        "base programming",
        "advanced programming",
        "sas studio",
        "sas viya",
        "sas viya workbench",
        "sas enterprise miner",
        "sas visual investigator",
        "enterprise guide and office analytics",
        "sas for microsoft 365",
        "jmp",
        # Data & Analytics
        "machine learning",
        "deep learning",
        "natural language processing",
        "nlp",
        "data analysis",
        "data visualization",
        "statistics",
        "basic statistics",
        "biostatistics",
        "text analytics",
        "visual analytics",
        "advanced analytics",
        "predictive analytics",
        "predictive modeling",
        "pattern discovery",
        "prescriptive analytics",
        "data literacy",
        "ai literacy",
        # Data Engineering & Governance
        "data engineering",
        "data integration",
        "data curation professional",
        "data governance",
        "data quality",
        "data access",
        "data acceleration",
        "etl",
        "feature engineering",
        # Analytics & Statistics
        "analytics",
        "regression",
        "regression modeling",
        "advanced regression",
        "classification",
        "time series",
        "forecasting and econometrics",
        "modeling",
        # Domain & Industry
        "intelligent decisioning",
        "intelligent planning",
        "prescriptive analytics",
        "predictive analytics",
        "fraud and security intelligence",
        "customer intelligence",
        "marketing research",
        "supply chain intelligence",
        "risk management",
        "health and life sciences",
        "social and behavioral research",
        # Infrastructure & DevOps
        "cloud",
        "aws",
        "azure",
        "gcp",
        "docker",
        "kubernetes",
        "deployment",
        "migration",
        "operations",
        "unix",
        "unix commands",
        # Security & Architecture
        "authentication",
        "encryption",
        "architecture",
        # Emerging Tech
        "internet of things",
        "event stream processing",
        # ML Frameworks
        "tensorflow",
        "pytorch",
        "scikit-learn",
        # Data Tools & Visualization
        "tableau",
        "power bi",
        "mapping",
        "microsoft windows",
        # APIs & Integration
        "rest api integration",
        # Soft Skills
        "technical troubleshooting",
        "cross-functional collaboration",
        "problem solving",
        "communication",
        "teamwork",
        "leadership",
        "critical thinking",
        "presentation",
        "stakeholder management",
        # Project Management
        "project management",
        "agile",
        "scrum",
        # Misc
        "custom web application",
    ]


def _normalize_skill_phrase(phrase: str) -> str:
    phrase = phrase.strip().lower()
    phrase = re.sub(r"\s+/\s+", " ", phrase)
    phrase = re.sub(r"[^a-z0-9]+", " ", phrase)
    phrase = re.sub(r"\s+", " ", phrase).strip()
    return phrase


def _keyword_matches(text: str, keywords: Iterable[str]) -> List[str]:
    found = set()
    for keyword in keywords:
        normalized_keyword = _normalize_skill_phrase(keyword)
        if not normalized_keyword:
            continue

        pattern = rf"\b{re.escape(normalized_keyword)}\b"
        if re.search(pattern, text, flags=re.IGNORECASE):
            found.add(normalized_keyword)
            found.add(keyword.lower())
    return sorted(found)


def _candidate_phrases(text: str) -> List[str]:
    phrases = set()
    for line in text.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        if len(cleaned.split()) <= 4:
            phrases.add(_normalize_skill_phrase(cleaned))
    return sorted(phrases)


def _split_skill_lines(section_text: str) -> List[str]:
    if not section_text:
        return []
    parts = re.split(r"[\/,]\\s*", section_text)
    return [p.strip() for p in parts if p.strip()]


def extract_skills(resume_text: str, custom_keywords: Optional[Iterable[str]] = None, max_skills: int = 80) -> List[str]:
    """Extract a list of skills from resume text using keyword matching and optional spaCy parsing."""
    normalized_text = normalize_text(resume_text)
    text = normalized_text.lower()
    keywords = set(default_skill_keywords())
    if custom_keywords:
        keywords.update(k.strip().lower() for k in custom_keywords if k)

    skills = set(_keyword_matches(text, keywords))
    normalized_keywords = {_normalize_skill_phrase(k): k.lower() for k in keywords}

    sections = extract_resume_sections(normalized_text)
    skills_section = sections.get("skills", "")
    if skills_section:
        for part in _split_skill_lines(skills_section):
            normalized_part = _normalize_skill_phrase(part)
            if not normalized_part:
                continue
            if normalized_part in normalized_keywords:
                skills.add(normalized_part)
                skills.add(normalized_keywords[normalized_part])
            elif any(word in normalized_part for word in [
                "javascript",
                "react",
                "java",
                "sql",
                "api",
                "troubleshooting",
                "collaboration",
                "problem",
                "solving",
                "python",
                "cloud",
                "data",
                "machine",
                "learning",
            ]):
                skills.add(normalized_part)

    for phrase in _candidate_phrases(text):
        normalized_phrase = _normalize_skill_phrase(phrase)
        if normalized_phrase in normalized_keywords:
            skills.add(normalized_phrase)
            skills.add(normalized_keywords[normalized_phrase])
        elif any(word in normalized_phrase for word in [
            "javascript",
            "react",
            "java",
            "sql",
            "api",
            "troubleshooting",
            "collaboration",
            "problem",
            "solving",
            "python",
            "cloud",
            "data",
            "machine",
            "learning",
        ]):
            skills.add(normalized_phrase)

    try:
        import spacy

        nlp = spacy.load("en_core_web_sm", disable=["parser", "textcat"])
        doc = nlp(text)
        for chunk in doc.noun_chunks:
            phrase = _normalize_skill_phrase(chunk.text)
            if phrase in normalized_keywords:
                skills.add(phrase)
                skills.add(normalized_keywords[phrase])
            elif any(word in phrase for word in [
                "javascript",
                "react",
                "java",
                "sql",
                "api",
                "troubleshooting",
                "collaboration",
                "problem",
                "solving",
                "python",
                "cloud",
                "data",
                "machine",
                "learning",
            ]):
                skills.add(phrase)
        for ent in doc.ents:
            phrase = _normalize_skill_phrase(ent.text)
            if phrase in normalized_keywords:
                skills.add(phrase)
                skills.add(normalized_keywords[phrase])
            elif any(word in phrase for word in [
                "javascript",
                "react",
                "java",
                "sql",
                "api",
                "troubleshooting",
                "collaboration",
                "problem",
                "solving",
                "python",
                "cloud",
                "data",
                "machine",
                "learning",
            ]):
                skills.add(phrase)
    except Exception:
        # spaCy is optional and only improves extraction quality
        pass

    return sorted(list(skills))[:max_skills]
    keywords = set(default_skill_keywords())
    if custom_keywords:
        keywords.update(k.strip().lower() for k in custom_keywords if k)

    skills = set(_keyword_matches(text, keywords))
    normalized_keywords = {_normalize_skill_phrase(k): k.lower() for k in keywords}

    for phrase in _candidate_phrases(text):
        normalized_phrase = _normalize_skill_phrase(phrase)
        if normalized_phrase in normalized_keywords:
            skills.add(normalized_phrase)
            skills.add(normalized_keywords[normalized_phrase])
        elif any(word in normalized_phrase for word in ["javascript", "react", "java", "sql", "api", "troubleshooting", "collaboration", "problem", "solving", "python", "cloud", "data", "machine", "learning"]):
            skills.add(normalized_phrase)

    try:
        import spacy

        nlp = spacy.load("en_core_web_sm", disable=["parser", "textcat"])
        doc = nlp(text)
        for chunk in doc.noun_chunks:
            phrase = _normalize_skill_phrase(chunk.text)
            if phrase in normalized_keywords:
                skills.add(phrase)
                skills.add(normalized_keywords[phrase])
            elif any(word in phrase for word in ["javascript", "react", "java", "sql", "api", "troubleshooting", "collaboration", "problem", "solving", "python", "cloud", "data", "machine", "learning"]):
                skills.add(phrase)
        for ent in doc.ents:
            phrase = _normalize_skill_phrase(ent.text)
            if phrase in normalized_keywords:
                skills.add(phrase)
                skills.add(normalized_keywords[phrase])
            elif any(word in phrase for word in ["javascript", "react", "java", "sql", "api", "troubleshooting", "collaboration", "problem", "solving", "python", "cloud", "data", "machine", "learning"]):
                skills.add(phrase)
    except Exception:
        # spaCy is optional and only improves extraction quality
        pass

    return sorted(list(skills))[:max_skills]
