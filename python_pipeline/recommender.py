import html
import re
import pandas as pd
from typing import List


def _normalize_title(t: str) -> str:
    """Normalize a course title for duplicate detection: case-folded,
    whitespace collapsed, symbols like ® / ™ / punctuation stripped —
    so titles that differ only in encoding or spacing are still caught
    as the same course."""
    t = str(t).lower()
    t = re.sub(r"[^\w\s]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def score_course_recommendations(feature_df: pd.DataFrame, weights: dict | None = None) -> pd.DataFrame:
    if weights is None:
        weights = {
            "skill_overlap": 0.26,
            "prereq_match": 0.16,
            "audience_match": 0.10,
            "pathway_match": 0.12,
            "level_match": 0.12,
            "tfidf_score": 0.10,
            "history_score": 0.10,
            "language_match": 0.04,
        }

    scored = feature_df.copy()
    for col in [
        "skill_overlap",
        "prereq_match",
        "audience_match",
        "pathway_match",
        "tfidf_score",
        "level_match",
        "language_match",
        "history_score",
    ]:
        if col not in scored.columns:
            scored[col] = 0.0

    scored["recommendation_score"] = (
        scored["skill_overlap"] * weights["skill_overlap"]
        + scored["prereq_match"] * weights["prereq_match"]
        + scored["audience_match"] * weights["audience_match"]
        + scored["pathway_match"] * weights["pathway_match"]
        + scored.get("level_match", 0.0) * weights.get("level_match", 0.0)
        + scored["tfidf_score"] * weights["tfidf_score"]
        + scored.get("history_score", 0.0) * weights.get("history_score", 0.0)
        + scored.get("language_match", 0.0) * weights.get("language_match", 0.0)
    )
    return scored.sort_values("recommendation_score", ascending=False).reset_index(drop=True)


def _dedupe_by_title(scored: pd.DataFrame) -> pd.DataFrame:
    """Given a score-sorted (descending) DataFrame, keep only the
    highest-scoring row per normalized title. Different course_codes
    that are really the same course under different codes (e.g. a
    web/live/on-demand variant sharing one title) are collapsed to
    whichever variant scored best."""
    if "title" not in scored.columns:
        return scored
    norm_titles = scored["title"].apply(_normalize_title)
    keep_mask = ~norm_titles.duplicated(keep="first")
    return scored.loc[keep_mask].reset_index(drop=True)


def recommend_top_courses(feature_df: pd.DataFrame, top_n: int = 10, weights: dict | None = None) -> pd.DataFrame:
    scored = score_course_recommendations(feature_df, weights)
    scored = scored.drop_duplicates(subset=["course_code"], keep="first")
    scored = _dedupe_by_title(scored)
    return scored.head(top_n)


def _normalize_course_text(value: str) -> str:
    value = html.unescape(str(value)).lower()
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _prerequisite_courses(prereq_text: str, courses_df: pd.DataFrame, completed_codes: set[str]) -> list[dict]:
    """Find catalog course titles named in prerequisite prose."""
    text = _normalize_course_text(prereq_text)
    if not text or text in {"none", "blank", "nan"}:
        return []

    matches = []
    titles = courses_df[["course_code", "title"]].dropna(subset=["title"])
    for _, course in titles.iterrows():
        title = str(course["title"]).strip()
        normalized_title = _normalize_course_text(title)
        if len(normalized_title) < 8:
            continue
        if re.search(rf"\b{re.escape(normalized_title)}\b", text):
            code = str(course["course_code"])
            matches.append({
                "course_code": code,
                "title": title,
                "completed": code in completed_codes,
            })
    return matches


def recommend_from_engagement(
    courses_df: pd.DataFrame,
    history_df: pd.DataFrame,
    top_n: int = 10,
) -> tuple[pd.DataFrame, dict]:
    """Recommend next courses from one learner's engagement profile."""
    status_weights = {"viewed": 0.3, "started": 0.6, "completed": 1.0}
    user_history = history_df.copy()
    user_history["status_weight"] = user_history["history_action"].map(status_weights).fillna(0.0)

    course_lookup = courses_df.set_index("course_code")
    learned_skills: dict[str, float] = {}
    learned_pathways: dict[str, float] = {}
    completed_codes = set()
    for _, row in user_history.iterrows():
        code = str(row["course_code"])
        weight = float(row["status_weight"])
        if row["history_action"] == "completed":
            completed_codes.add(code)
        if code not in course_lookup.index:
            continue
        course = course_lookup.loc[code]
        for skill in course.get("skills_list", []):
            normalized = str(skill).strip().lower()
            if normalized:
                learned_skills[normalized] = learned_skills.get(normalized, 0.0) + weight
        pathway = str(course.get("primary_pathway", "")).strip()
        if pathway:
            learned_pathways[pathway] = learned_pathways.get(pathway, 0.0) + weight

    total_pathway_weight = sum(learned_pathways.values()) or 1.0
    learned_skill_count = len(learned_skills) or 1
    ranked_rows = []
    for _, row in courses_df.iterrows():
        code = str(row.get("course_code", ""))
        if code in completed_codes:
            continue
        prerequisite_courses = _prerequisite_courses(
            row.get("prerequisites", ""), courses_df, completed_codes
        )
        prerequisite_match = (
            sum(course["completed"] for course in prerequisite_courses)
            / len(prerequisite_courses)
            if prerequisite_courses
            else 1.0
        )
        skills = {str(skill).strip().lower() for skill in row.get("skills_list", []) if str(skill).strip()}
        matched_skills = skills.intersection(learned_skills)
        # Cap each skill at completed-level evidence so repeated engagement
        # snapshots cannot inflate a score indefinitely.
        weighted_matches = sum(min(learned_skills[skill], 1.0) for skill in matched_skills)
        course_skill_coverage = weighted_matches / max(1, len(skills))
        learned_skill_coverage = weighted_matches / max(1.0, sum(learned_skills.values()))
        skill_overlap = 0.7 * course_skill_coverage + 0.3 * learned_skill_coverage
        pathway = str(row.get("primary_pathway", "")).strip()
        pathway_match = min(learned_pathways.get(pathway, 0.0) / total_pathway_weight * 2.0, 1.0)
        ranked_rows.append({
            "course_code": code,
            "title": str(row.get("title", "")),
            "primary_pathway": pathway,
            "recommendation_score": round(0.8 * skill_overlap + 0.2 * pathway_match, 4),
            "skill_overlap": round(skill_overlap, 4),
            "prereq_match": round(prerequisite_match, 4),
            "prerequisite_courses": prerequisite_courses,
            "audience_match": 0.0,
            "pathway_match": round(pathway_match, 4),
            "level_match": 0.0,
            "tfidf_score": 0.0,
            "history_score": 0.0,
            "language": str(row.get("language", "en")),
            "language_match": 1.0,
        })

    ranked = pd.DataFrame(ranked_rows)
    if not ranked.empty:
        ranked = ranked.sort_values(["recommendation_score", "course_code"], ascending=[False, True])
        ranked = _dedupe_by_title(ranked).head(top_n)
    completed_details = []
    for code in sorted(completed_codes):
        if code in course_lookup.index:
            course = course_lookup.loc[code]
            completed_details.append({
                "course_code": code,
                "title": str(course.get("title", "")),
                "primary_pathway": str(course.get("primary_pathway", "")),
            })
    profile = {
        "completed_courses": len(completed_codes),
        "engagement_courses": int(len(user_history)),
        "completed_course_details": completed_details,
        "learned_skills": [skill for skill, _ in sorted(learned_skills.items(), key=lambda item: (-item[1], item[0]))],
        "focus_pathways": [pathway for pathway, _ in sorted(learned_pathways.items(), key=lambda item: (-item[1], item[0]))],
        "prerequisite_checks": [
            {
                "course_code": str(row.get("course_code", "")),
                "title": str(row.get("title", "")),
                "prerequisite_courses": row.get("prerequisite_courses", []),
                "prereq_match": float(row.get("prereq_match", 1.0)),
            }
            for _, row in ranked.iterrows()
            if row.get("prerequisite_courses")
        ],
    }
    return ranked.reset_index(drop=True), profile


def recommend_curriculum_and_pathway(feature_df: pd.DataFrame, courses_df: pd.DataFrame, top_n: int = 20, weights: dict | None = None) -> tuple[str, str]:
    """Recommend a curriculum and primary pathway for the user.

    Looks at the top N scored courses and picks the curriculum with the highest
    cumulative recommendation score, then selects the most-supported primary
    pathway within that curriculum.
    """
    scored = score_course_recommendations(feature_df, weights)
    top = scored.drop_duplicates(subset=["course_code"], keep="first")
    top = _dedupe_by_title(top).head(top_n)
    merged = top.merge(
        courses_df[["course_code", "curriculum", "primary_pathway"]], on="course_code", how="left"
    )
    if merged.empty:
        return ("", "")

    curriculum_scores = merged.groupby("curriculum")["recommendation_score"].sum()
    recommended_curriculum = curriculum_scores.idxmax()

    pathway_scores = (
        merged[merged["curriculum"] == recommended_curriculum]
        .groupby("primary_pathway")["recommendation_score"]
        .sum()
    )
    recommended_pathway = pathway_scores.idxmax()
    return (recommended_curriculum, recommended_pathway)