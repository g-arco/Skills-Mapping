import hashlib
import html
import re
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

HANDOFF_DIR = Path(__file__).resolve().parent.parent / "data" / "handoff"
EMBED_CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache" / "embeddings"

_COURSE_TFIDF_VECTOR = None
_COURSE_TFIDF_MATRIX = None
_COURSE_TFIDF_DOCS = None

# In-memory caches so a single process never reloads the model or
# re-encodes the same course catalog more than once.
_SENTENCE_MODEL = None
_SENTENCE_MODEL_NAME = None
_COURSE_EMBED_CACHE_KEY = None
_COURSE_EMBED_CACHE_VECS = None


def _get_course_tfidf(courses_df: pd.DataFrame):
    global _COURSE_TFIDF_VECTOR, _COURSE_TFIDF_MATRIX, _COURSE_TFIDF_DOCS
    docs = courses_df["combined_text"].fillna("").tolist()
    if _COURSE_TFIDF_MATRIX is None or _COURSE_TFIDF_DOCS is not docs:
        _COURSE_TFIDF_VECTOR = TfidfVectorizer(
            ngram_range=(1, 2),
            max_features=2000,
            stop_words="english",
        )
        _COURSE_TFIDF_MATRIX = _COURSE_TFIDF_VECTOR.fit_transform(docs)
        _COURSE_TFIDF_DOCS = docs
    return _COURSE_TFIDF_VECTOR, _COURSE_TFIDF_MATRIX


def _course_corpus_hash(courses_df: pd.DataFrame) -> str:
    """Stable content hash of the course catalog (code + text) so the
    embedding cache is automatically invalidated if the catalog changes."""
    codes = courses_df["course_code"].astype(str)
    texts = courses_df["combined_text"].fillna("").astype(str)
    joined = "\n".join((codes + "||" + texts).tolist())
    return hashlib.md5(joined.encode("utf-8")).hexdigest()


def _get_sentence_model(model_name: str = "all-MiniLM-L6-v2"):
    """Load the SentenceTransformer once per process and reuse it."""
    global _SENTENCE_MODEL, _SENTENCE_MODEL_NAME
    from sentence_transformers import SentenceTransformer

    if _SENTENCE_MODEL is None or _SENTENCE_MODEL_NAME != model_name:
        _SENTENCE_MODEL = SentenceTransformer(model_name)
        _SENTENCE_MODEL_NAME = model_name
    return _SENTENCE_MODEL


def _get_course_embeddings(courses_df: pd.DataFrame, model, use_disk_cache: bool = True) -> np.ndarray:
    """
    Return embeddings for every row in courses_df, reusing:
      1) an in-memory cache within this process, then
      2) a disk cache (data/cache/embeddings/*.npy) across runs,
    before falling back to actually encoding with the model.
    """
    global _COURSE_EMBED_CACHE_KEY, _COURSE_EMBED_CACHE_VECS

    corpus_hash = _course_corpus_hash(courses_df)
    cache_key = f"{_SENTENCE_MODEL_NAME}_{corpus_hash}"

    # 1) in-memory (same process, e.g. build_feature_matrix called twice)
    if _COURSE_EMBED_CACHE_KEY == cache_key and _COURSE_EMBED_CACHE_VECS is not None:
        return _COURSE_EMBED_CACHE_VECS

    # 2) on-disk (across separate pipeline runs)
    cache_path = EMBED_CACHE_DIR / f"course_embeddings_{cache_key}.npy"
    if use_disk_cache and cache_path.exists():
        course_vecs = np.load(cache_path)
        print(f"[FeatureMatrix] Loaded cached course embeddings ({len(course_vecs)} rows) ← {cache_path}")
        _COURSE_EMBED_CACHE_KEY = cache_key
        _COURSE_EMBED_CACHE_VECS = course_vecs
        return course_vecs

    # 3) compute from scratch
    course_vecs = model.encode(courses_df["combined_text"].fillna("").tolist(), show_progress_bar=True)
    course_vecs = np.asarray(course_vecs)

    if use_disk_cache:
        EMBED_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        np.save(cache_path, course_vecs)
        print(f"[FeatureMatrix] Cached course embeddings ({len(course_vecs)} rows) → {cache_path}")

    _COURSE_EMBED_CACHE_KEY = cache_key
    _COURSE_EMBED_CACHE_VECS = course_vecs
    return course_vecs


# Common language name / locale variants -> ISO 639-1 two-letter code.
# Covers full English names, native names, and locale-tagged codes
# (e.g. "en-US", "zh_CN") that might appear in a course catalog.
_LANGUAGE_TO_ISO639_1 = {
    "english": "en", "en": "en",
    "spanish": "es", "es": "es", "español": "es",
    "french": "fr", "fr": "fr", "français": "fr",
    "german": "de", "de": "de", "deutsch": "de",
    "portuguese": "pt", "pt": "pt", "português": "pt",
    "italian": "it", "it": "it", "italiano": "it",
    "dutch": "nl", "nl": "nl",
    "japanese": "ja", "ja": "ja", "jp": "ja",
    "chinese": "zh", "zh": "zh", "mandarin": "zh", "cn": "zh",
    "korean": "ko", "ko": "ko",
    "russian": "ru", "ru": "ru",
    "arabic": "ar", "ar": "ar",
    "hindi": "hi", "hi": "hi",
    "polish": "pl", "pl": "pl",
    "swedish": "sv", "sv": "sv",
    "turkish": "tr", "tr": "tr",
    "vietnamese": "vi", "vi": "vi",
    "thai": "th", "th": "th",
    "indonesian": "id", "id": "id",
}


def _to_iso639_1(lang: str | None) -> str:
    """Normalize a language name, locale tag (en-US, zh_CN), or existing
    ISO 639-1 code down to a bare two-letter ISO 639-1 code. Falls back
    to "en" if the value is missing or unrecognized."""
    if not lang or not str(lang).strip():
        return "en"
    s = str(lang).strip().lower()
    # Strip locale/region suffixes: "en-US", "en_US", "zh-Hans" -> "en", "zh"
    s = re.split(r"[-_]", s)[0]
    if s in _LANGUAGE_TO_ISO639_1:
        return _LANGUAGE_TO_ISO639_1[s]
    if len(s) == 2 and s.isalpha():
        # Unrecognized but already looks like an ISO 639-1 code — pass through.
        return s
    return "en"

def parse_course_history(file_obj, email: str | None = None) -> pd.DataFrame:
    """Parse the SAS EDU engagements history CSV and normalize its columns."""
    df = pd.read_csv(file_obj, low_memory=False)
    column_map = {
        "ecode": "course_code",
        "productcode": "course_code",
        "course_code": "course_code",
        "coursetype": "course_type",
        "elearningplatform": "elearning_platform",
        "e_learning_platform": "elearning_platform",
        "email": "email",
        "sasemail": "email",
        "status": "history_action",
        "progress_course": "history_progress",
        "progress_module": "progress_module",
        "numstarted": "num_started",
        "numviewed": "num_viewed",
        "numcompleted": "num_completed",
    }
    rename_map = {}
    for col in df.columns:
        key = col.strip().lower()
        if key in column_map:
            rename_map[col] = column_map[key]
    df = df.rename(columns=rename_map)

    # Multiple source aliases (for example `email` and `sasemail`) can map to
    # the same canonical field. Coalesce them so downstream indexing returns a
    # Series rather than a DataFrame.
    for canonical in set(rename_map.values()):
        matching = df.loc[:, df.columns == canonical]
        if matching.shape[1] > 1:
            merged = matching.replace({"": pd.NA}).bfill(axis=1).iloc[:, 0]
            df = df.drop(columns=[canonical])
            df[canonical] = merged

    required = ["course_code", "elearning_platform", "history_action", "history_progress"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Course history CSV missing required columns: {missing}")

    df = df.copy()
    df["course_code"] = df["course_code"].astype(str).str.strip()
    df["email"] = df.get("email", "").astype(str).str.strip().str.lower()
    df["elearning_platform"] = df["elearning_platform"].astype(str).str.strip().str.lower()
    df["history_action"] = df["history_action"].astype(str).str.strip().str.lower()

    if email and str(email).strip():
        requested_email = str(email).strip().lower()
        df = df[df["email"] == requested_email]

    def normalize_progress(value):
        if pd.isna(value):
            return 0.0
        if isinstance(value, str):
            value = value.strip().replace("%", "")
        try:
            return float(value)
        except Exception:
            return 0.0

    df["history_progress"] = df["history_progress"].apply(normalize_progress)
    df.loc[(df["history_progress"] > 1.0) & (df["history_progress"] <= 100.0), "history_progress"] = (
        df.loc[(df["history_progress"] > 1.0) & (df["history_progress"] <= 100.0), "history_progress"] / 100.0
    )
    df["history_progress"] = df["history_progress"].clip(0.0, 1.0)

    valid_actions = {"completed", "started", "viewed"}
    df = df[df["history_action"].isin(valid_actions)]
    df = df[df["elearning_platform"] == "current"]
    df = df[df["course_code"].astype(bool)]

    if df.empty:
        return df[["course_code", "email", "elearning_platform", "history_action", "history_progress"]]

    df = df.sort_values(["course_code", "history_progress", "history_action"], ascending=[True, False, True])
    df = df.drop_duplicates(subset=["course_code"], keep="first").reset_index(drop=True)
    return df[["course_code", "email", "elearning_platform", "history_action", "history_progress"]]


def attach_course_history(courses_df: pd.DataFrame, history_df: pd.DataFrame) -> pd.DataFrame:
    courses = courses_df.copy()
    if "course_code" not in courses.columns:
        raise ValueError("Course catalog is missing course_code column.")

    history_map = history_df.set_index("course_code")["history_action"].to_dict()
    progress_map = history_df.set_index("course_code")["history_progress"].to_dict()

    courses["history_action"] = courses["course_code"].map(history_map).fillna("")
    courses["history_progress"] = courses["course_code"].map(progress_map).fillna(0.0)
    return courses

def generate_resume_id(text: str) -> str:
    return "R_" + hashlib.md5(text.encode()).hexdigest()[:10].upper()


def _prerequisite_terms(prereq_text: str, vocabulary: set[str]) -> list[str]:
    """Extract recognizable prerequisite concepts from catalog prose."""
    text = html.unescape(str(prereq_text))
    text = re.sub(r"<\s*li\s*>", ". ", text, flags=re.IGNORECASE)
    text = re.sub(r"<\s*br\s*/?\s*>", ". ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip().lower()

    if not text or (
        re.search(r"\b(no|none|not required|not have any|required prerequisites?)\b", text)
        and re.search(r"\b(prerequisite|requirement)\w*\b", text)
    ):
        return []

    terms = sorted(
        {term for term in vocabulary if term and len(term.split()) > 1},
        key=lambda term: (-len(term.split()), -len(term)),
    )
    found = []
    occupied: list[tuple[int, int]] = []
    for term in terms:
        match = re.search(rf"\b{re.escape(term)}\b", text)
        if not match:
            continue
        if any(match.start() < end and match.end() > start for start, end in occupied):
            continue
        found.append(term)
        occupied.append((match.start(), match.end()))

    for term in sorted(
        {term for term in vocabulary if len(term.split()) == 1},
        key=lambda value: (-len(value), value),
    ):
        match = re.search(rf"\b{re.escape(term)}\b", text)
        covered_by_longer_term = any(
            len(longer_term.split()) > 1
            and re.search(rf"\b{re.escape(longer_term)}\b", text)
            and re.search(rf"\b{re.escape(term)}\b", longer_term)
            for longer_term in vocabulary
        )
        if match and not covered_by_longer_term and not any(
            match.start() < end and match.end() > start for start, end in occupied
        ):
            found.append(term)
            occupied.append((match.start(), match.end()))
    return sorted(set(found), key=lambda term: text.find(term))


def _prerequisite_match(prereq_text: str, resume_skills: set[str], vocabulary: set[str]) -> float:
    terms = _prerequisite_terms(prereq_text, vocabulary)
    if not terms:
        return 1.0

    normalized_skills = {
        re.sub(r"[^a-z0-9]+", " ", skill.lower()).strip()
        for skill in resume_skills
    }
    matched = 0
    for term in terms:
        term_tokens = set(term.split())
        if any(
            skill == term
            or set(skill.split()).issubset(term_tokens)
            or term_tokens.issubset(set(skill.split()))
            for skill in normalized_skills
            if skill
        ):
            matched += 1
    return round(matched / len(terms), 4)


def build_feature_matrix(
    resume_text: str,
    extracted_skills: list[str],
    courses_df: pd.DataFrame,
    user_level: str = "beginner",
    target_pathways: list[str] | None = None,
    resume_audience_terms: list[str] | None = None,
    use_disk_cache: bool = True,
    user_language: str = "en",
) -> pd.DataFrame:
    resume_id = generate_resume_id(resume_text)
    skill_set = {s.lower() for s in extracted_skills}
    n = len(courses_df)
    user_language_iso = _to_iso639_1(user_language)

    # Derive course skills from `combined_text` when `skills_list` is empty
    try:
        from python_pipeline.skills import default_skill_keywords, _normalize_skill_phrase

        keyword_norm = [_normalize_skill_phrase(k) for k in default_skill_keywords()]

        def _derive_skills_from_text(text: str) -> list[str]:
            text_norm = re.sub(r"[^a-z0-9]+", " ", str(text).lower())
            found = []
            for k in keyword_norm:
                if re.search(rf"\b{re.escape(k)}\b", text_norm):
                    found.append(k)
            return found
    except Exception:
        # Fallback: no derived skills available
        def _derive_skills_from_text(text: str) -> list[str]:
            return []

    course_skill_lists = []
    for _, row in courses_df.iterrows():
        existing = row.get("skills_list", [])
        normalized_existing = [s.strip().lower() for s in (existing or []) if str(s).strip()]
        if normalized_existing:
            course_skill_lists.append(normalized_existing)
        else:
            course_skill_lists.append(_derive_skills_from_text(row.get("combined_text", "")))

    def _overlap(skills_list):
        if not skills_list:
            return 0.0
        return round(sum(1 for s in skills_list if s.lower() in skill_set) / len(skills_list), 4)

    skill_overlap = [ _overlap(sk) for sk in course_skill_lists ]
    skill_overlap = np.array(skill_overlap, dtype=float)

    try:
        # compute TF-IDF corpus (used as fallback and for `tfidf_score`)
        corpus = courses_df["combined_text"].fillna("").tolist() + [resume_text]
        tfidf = TfidfVectorizer(ngram_range=(1, 2), max_features=3000, stop_words="english")
        matrix = tfidf.fit_transform(corpus)
        tfidf_scores = cosine_similarity(matrix[-1], matrix[:-1])[0].round(4)

        model = _get_sentence_model("all-MiniLM-L6-v2")
        resume_text_for_encoding = " ".join(extracted_skills) or resume_text[:500]
        resume_vec = model.encode([resume_text_for_encoding])
        course_vecs = _get_course_embeddings(courses_df, model, use_disk_cache=use_disk_cache)
        sims = cosine_similarity(resume_vec, course_vecs)[0]
        gap_score = (1 - np.clip(sims, 0, 1)).round(4)
    except ImportError:
        # sentence-transformers not available — fall back to TF-IDF similarity
        try:
            corpus
        except NameError:
            corpus = courses_df["combined_text"].fillna("").tolist() + [resume_text]
            tfidf = TfidfVectorizer(ngram_range=(1, 2), max_features=3000, stop_words="english")
            matrix = tfidf.fit_transform(corpus)
            tfidf_scores = cosine_similarity(matrix[-1], matrix[:-1])[0].round(4)
        gap_score = (1 - tfidf_scores).round(4)
        print("[FeatureMatrix] sentence-transformers not installed; using TF-IDF fallback for gap_score. To enable better semantic scoring: pip install sentence-transformers")
    except Exception:
        # any other error — fall back to TF-IDF or constant
        try:
            gap_score = (1 - tfidf_scores).round(4)
        except Exception:
            gap_score = np.ones(n, dtype=float)

    prerequisite_vocabulary = set(keyword_norm) | skill_set
    prereq_match = courses_df["prerequisites"].apply(
        lambda prereq: _prerequisite_match(prereq, skill_set, prerequisite_vocabulary)
    ).values

    def _token_set(text: str) -> set[str]:
        return {token for token in re.findall(r"[a-z0-9]+", str(text).lower())}

    resume_audience_tokens = set()
    for term in resume_audience_terms or []:
        resume_audience_tokens |= _token_set(term)
    resume_skill_tokens = set()
    for skill in extracted_skills:
        resume_skill_tokens |= _token_set(skill)
    resume_context_tokens = resume_audience_tokens | resume_skill_tokens
    level_keywords = {
        "beginner": ["beginner", "all", "introductory", "entry", "foundation"],
        "intermediate": ["intermediate", "all", "mid", "practitioner"],
        "advanced": ["advanced", "all", "expert", "senior", "professional"],
    }
    accepted = level_keywords.get(user_level.lower(), ["all"])
    def _audience_match(audience_str: str) -> float:
        audience_tokens = _token_set(audience_str)
        if not audience_tokens:
            return 0.0
        level_score = 1.0 if any(kw in audience_tokens for kw in accepted) else 0.0
        overlap = 0.0
        if resume_context_tokens:
            overlap = len(audience_tokens & resume_context_tokens) / max(1, len(audience_tokens | resume_context_tokens))
        return round(max(level_score, overlap), 4)

    audience_match = courses_df["audience"].apply(_audience_match).values

    # Match course LEVEL against the requested user_level (beginner/intermediate/advanced)
    level_match = courses_df["level"].apply(
        lambda l: int(any(kw in str(l).lower() for kw in accepted))
    ).values

    def _pathway_match(pathway_str: str) -> float:
        pathway_tokens = _token_set(pathway_str)
        if not pathway_tokens:
            return 0.0
        if target_pathways:
            target_set = {p.lower() for p in target_pathways}
            return float(any(target in str(pathway_str).lower() for target in target_set))
        if not resume_context_tokens:
            return 0.0
        overlap = len(pathway_tokens & resume_context_tokens) / max(1, len(pathway_tokens | resume_context_tokens))
        return round(overlap, 4)

    pathway_match = courses_df["primary_pathway"].apply(_pathway_match).values

    # Language match: normalize whatever's in the catalog's `language`
    # column (full name, locale tag, or code) to ISO 639-1 and compare
    # against the requested user_language. Courses with no language info
    # are treated as matching (assume "en" / don't penalize missing data).
    if "language" in courses_df.columns:
        course_language_iso = courses_df["language"].apply(_to_iso639_1)
    else:
        course_language_iso = pd.Series(["en"] * n, index=courses_df.index)
    language_match = (course_language_iso == user_language_iso).astype(int).values

    # tfidf_scores already computed above (used as a fallback and output column)

    history_score = np.zeros(n, dtype=float)
    if "history_action" in courses_df.columns:
        history_action_values = courses_df["history_action"].astype(str).str.lower().fillna("")
        history_progress_values = pd.to_numeric(courses_df.get("history_progress", 0.0), errors="coerce").fillna(0.0)
        action_weight = history_action_values.map({"completed": 1.0, "started": 0.6, "viewed": 0.3}).fillna(0.0)
        history_score = (action_weight * history_progress_values).astype(float).values

    df = pd.DataFrame(
        {
            "resume_id": resume_id,
            "course_code": courses_df["course_code"].values,
            "title": courses_df["title"].values,
            "primary_pathway": courses_df["primary_pathway"].values,
            "skill_overlap": skill_overlap,
            "gap_score": gap_score,
            "prereq_match": prereq_match,
            "audience_match": audience_match.astype(int),
            "level_match": level_match.astype(int),
            "pathway_match": pathway_match.astype(int),
            "tfidf_score": tfidf_scores,
            "language": course_language_iso.values,
            "language_match": language_match,
            "history_score": history_score,
        }
    )
    return df


def build_and_export_features(
    resume_text: str,
    extracted_skills: list[str],
    courses_df: pd.DataFrame,
    user_level: str = "beginner",
    target_pathways: list[str] | None = None,
    resume_audience_terms: list[str] | None = None,
    output_path: Path | None = None,
    feature_df: pd.DataFrame | None = None,
    user_language: str = "en",
) -> Path:
    """
    Writes a feature matrix CSV. If `feature_df` is already computed
    (e.g. by an earlier call to build_feature_matrix), pass it in here
    to avoid recomputing embeddings a second time.
    """
    HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
    df = feature_df if feature_df is not None else build_feature_matrix(
        resume_text,
        extracted_skills,
        courses_df,
        user_level,
        target_pathways,
        resume_audience_terms=resume_audience_terms,
        user_language=user_language,
    )
    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = HANDOFF_DIR / f"feature_matrix_{ts}.csv"
    df.to_csv(output_path, index=False)
    print(f"[Exporter] Feature matrix written → {output_path}")
    return output_path


def load_sas_scores(scores_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(scores_csv)
    score_col_candidates = ["P_label1", "P_1", "P1", "predicted_prob", "score"]
    score_col = next((c for c in score_col_candidates if c in df.columns), None)
    if score_col is None:
        float_cols = df.select_dtypes(include="float").columns.tolist()
        if float_cols:
            score_col = float_cols[0]
        else:
            raise ValueError(f"Cannot find a score column in {scores_csv}. Available columns: {list(df.columns)}")
    df = df.rename(columns={score_col: "sas_score"})
    df["sas_score"] = df["sas_score"].clip(0, 1)
    return df.sort_values("sas_score", ascending=False).reset_index(drop=True)