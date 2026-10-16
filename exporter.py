"""
python_pipeline/exporter.py
────────────────────────────
Builds the feature matrix from resume + course data,
then writes it to data/handoff/feature_matrix.csv
ready for you to upload into SAS Studio.

This replaces the swat CAS bridge entirely.
No SAS credentials needed. No network calls.
"""

import hashlib
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

HANDOFF_DIR = Path(__file__).resolve().parent.parent / "data" / "handoff"


def generate_resume_id(text: str) -> str:
    return "R_" + hashlib.md5(text.encode()).hexdigest()[:10].upper()


def build_and_export_features(
    resume_text: str,
    resume_sections: dict,
    extracted_skills: list[str],          # flat list from skill_extractor
    courses_df: pd.DataFrame,
    user_level: str = "beginner",
    target_pathways: list[str] = None,
    output_path: Path = None,
) -> Path:
    """
    Build one feature row per course, write to CSV, return the file path.

    Columns written
    ───────────────
    resume_id        str
    course_code      str
    title            str
    primary_pathway  str
    skill_overlap    float  [0–1]   fraction of course skills candidate already has
    gap_score        float  [0–1]   semantic distance (1 − cosine sim)
    prereq_match     float  [0–1]   fraction of prereqs met
    audience_match   int    {0,1}
    pathway_match    int    {0,1}
    tfidf_score      float  [0–1]   TF-IDF relevance of course to resume
    """
    HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
    resume_id = generate_resume_id(resume_text)
    skill_set  = {s.lower() for s in extracted_skills}
    n          = len(courses_df)

    # ── 1. Skill overlap ─────────────────────────────────────
    def _overlap(skills_list):
        if not skills_list:
            return 0.0
        return round(sum(1 for s in skills_list if s in skill_set) / len(skills_list), 4)

    skill_overlap = courses_df["skills_list"].apply(_overlap).values

    # ── 2. Semantic gap (sentence-transformers) ───────────────
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")
        resume_vec  = model.encode([" ".join(extracted_skills) or resume_text[:500]])
        course_vecs = model.encode(courses_df["combined_text"].tolist(), show_progress_bar=False)
        sims        = cosine_similarity(resume_vec, course_vecs)[0]
        gap_score   = (1 - np.clip(sims, 0, 1)).round(4)
    except ImportError:
        # fallback: TF-IDF cosine
        gap_score = np.ones(n, dtype=float)

    # ── 3. Prerequisite match ─────────────────────────────────
    def _prereq(prereq_str):
        prereqs = [p.strip().lower() for p in str(prereq_str).split(",") if p.strip()]
        if not prereqs:
            return 1.0
        return round(sum(1 for p in prereqs if p in skill_set) / len(prereqs), 4)

    prereq_match = courses_df["prerequisites"].apply(_prereq).values

    # ── 4. Audience match ─────────────────────────────────────
    level_keywords = {
        "beginner":     ["beginner", "all", "introductory", "entry", "foundation"],
        "intermediate": ["intermediate", "all", "mid", "practitioner"],
        "advanced":     ["advanced", "all", "expert", "senior", "professional"],
    }
    accepted = level_keywords.get(user_level.lower(), ["all"])
    audience_match = courses_df["audience"].apply(
        lambda a: int(any(kw in a.lower() for kw in accepted))
    ).values

    # ── 5. Pathway match ─────────────────────────────────────
    if target_pathways:
        target_set = {p.lower() for p in target_pathways}
        pathway_match = courses_df["primary_pathway"].apply(
            lambda p: int(p.lower() in target_set)
        ).values
    else:
        pathway_match = np.ones(n, dtype=int)

    # ── 6. TF-IDF relevance ──────────────────────────────────
    corpus       = courses_df["combined_text"].tolist() + [resume_text]
    tfidf        = TfidfVectorizer(ngram_range=(1, 2), max_features=3000, stop_words="english")
    matrix       = tfidf.fit_transform(corpus)
    tfidf_scores = cosine_similarity(matrix[-1], matrix[:-1])[0].round(4)

    # ── Assemble ─────────────────────────────────────────────
    df = pd.DataFrame({
        "resume_id":       resume_id,
        "course_code":     courses_df["course_code"].values,
        "title":           courses_df["title"].values,
        "primary_pathway": courses_df["primary_pathway"].values,
        "skill_overlap":   skill_overlap,
        "gap_score":       gap_score,
        "prereq_match":    prereq_match,
        "audience_match":  audience_match.astype(int),
        "pathway_match":   pathway_match.astype(int),
        "tfidf_score":     tfidf_scores,
    })

    # ── Write CSV ─────────────────────────────────────────────
    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = HANDOFF_DIR / f"feature_matrix_{ts}.csv"

    df.to_csv(output_path, index=False)
    print(f"[Exporter] Feature matrix written → {output_path}")
    print(f"[Exporter] {len(df)} rows ({n} courses) for resume {resume_id}")
    return output_path


def load_sas_scores(scores_csv: Path) -> pd.DataFrame:
    """
    Read the scores.csv that SAS Studio exported after PROC FOREST/LOGISTIC.

    Expected columns from SAS:
        course_code   str
        P_label1      float   (probability of recommendation — from PROC LOGISTIC)
        I_label       int     (predicted class)
        INTO          float   (or P_1 depending on SAS proc used)

    Falls back gracefully if column names differ.
    """
    df = pd.read_csv(scores_csv)

    # Normalise the score column name (SAS uses different names per proc)
    score_col_candidates = ["P_label1", "P_1", "P1", "predicted_prob", "score"]
    score_col = next((c for c in score_col_candidates if c in df.columns), None)

    if score_col is None:
        # Last resort: use the first float column that isn't course identifiers
        float_cols = df.select_dtypes(include="float").columns.tolist()
        if float_cols:
            score_col = float_cols[0]
        else:
            raise ValueError(
                f"Cannot find a score column in {scores_csv}.\n"
                f"Available columns: {list(df.columns)}"
            )

    df = df.rename(columns={score_col: "sas_score"})
    df["sas_score"] = df["sas_score"].clip(0, 1)
    return df.sort_values("sas_score", ascending=False).reset_index(drop=True)
