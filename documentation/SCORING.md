# Scoring Overview

This document explains how the Skills Mapping project computes course recommendations from a resume and course catalog.

## 1. Feature matrix construction

The scoring pipeline builds a feature matrix in `python_pipeline/feature_matrix.py` via `build_feature_matrix()`.

### Inputs
- `resume_text`: user resume content, plain text or PDF-extracted text
- `extracted_skills`: skills extracted from the resume
- `courses_df`: course catalog metadata
- `user_level`: requested learning level (`beginner`, `intermediate`, `advanced`)
- `target_pathways`: optional target learning pathways
- `resume_audience_terms`: optional audience/profile terms
- `user_language`: desired language code, default `en`

### Output feature columns
The feature matrix returns one row per course with these important columns:

- `skill_overlap`
  - Fraction of course skills that appear in the resume skill set.
  - If `courses_df` contains a `skills_list`, those skills are used.
  - Otherwise, skills are derived from the course `combined_text` using keyword matching.

- `gap_score`
  - Represents how different the course is from the resume.
  - Computed as `1 - similarity(resume, course)`.
  - If `sentence-transformers` is installed, semantic embeddings are used.
  - Otherwise, it falls back to TF-IDF cosine similarity.

- `prereq_match`
  - Ratio of course prerequisite terms satisfied by the resume skill set.
  - Calculated as matched prereqs / total prereqs.

- `audience_match`
  - Binary/int score based on course `audience` text and resume audience context.
  - If a requested `user_level` keyword appears in the audience text, this score is 1.
  - Otherwise it is the token overlap between the course audience and resume audience/skills.

- `level_match`
  - Set to 1 when the course `level` text matches the requested user level.
  - Otherwise 0.

- `pathway_match`
  - If `target_pathways` is provided, this is 1 when the course `primary_pathway` contains any target pathway.
  - Otherwise it is the token overlap of course pathway tokens with resume context tokens.

- `language`
  - Normalized language code for the course (`en`, `es`, etc.).
  - Uses ISO 639-1 normalization.

- `language_match`
  - 1 when the normalized course language equals `user_language`.
  - Courses with missing language are treated as matching.

- `tfidf_score`
  - Cosine similarity between the resume text and the course `combined_text` using TF-IDF vectors.
  - Used both as a feature and as fallback for semantic similarity.

- `history_score`
  - Computed only when `courses_df` contains `history_action` and `history_progress`.
  - Per-course score formula:
    - `completed` uses weight 1.0
    - `started` uses weight 0.6
    - `viewed` uses weight 0.3
    - result = action_weight * history_progress
  - Example: a completed course with 85% progress becomes `0.85`.

## 2. History parsing and course history attachment

Course history is parsed in `python_pipeline/feature_matrix.py` via `parse_course_history()`.

Key behaviors:
- Normalizes email to lowercase and strips whitespace.
- Keeps only courses with `elearning_platform == "current"`.
- Normalizes progress values like `85%` to `0.85`.
- Keeps only valid history actions: `completed`, `started`, `viewed`.
- Deduplicates by `course_code`, keeping the row with the highest progress.

History rows are attached to the catalog with `attach_course_history()`, which maps the best-matching course history row onto each catalog course.

## 3. Recommendation scoring

The recommendation score is computed in `python_pipeline/recommender.py` using `score_course_recommendations()`.

### Default scoring weights
The default linear blend uses these weights:

- `skill_overlap`: 0.26
- `prereq_match`: 0.16
- `audience_match`: 0.10
- `pathway_match`: 0.12
- `level_match`: 0.12
- `tfidf_score`: 0.10
- `history_score`: 0.10
- `language_match`: 0.04

### Final score formula
```
recommendation_score =
    skill_overlap * 0.26
  + prereq_match * 0.16
  + audience_match * 0.10
  + pathway_match * 0.12
  + level_match * 0.12
  + tfidf_score * 0.10
  + history_score * 0.10
  + language_match * 0.04
```

Courses missing a feature column are treated as 0 for that feature.

### Ranking
- The scored courses are sorted descending by `recommendation_score`.
- `recommend_top_courses()` also deduplicates by `course_code` and by normalized `title`.
- Deduplication keeps the highest-scoring variant for courses that share the same normalized title.

## 4. Practical interpretation

- Higher `skill_overlap` means the course teaches skills already present in the resume.
- Higher `gap_score` means the course covers new or different content relative to the resume.
- Higher `prereq_match` means the resume already satisfies more of the course prerequisites.
- `history_score` boosts courses already familiar to the user, especially completed courses.
- `language_match` ensures the course is in the requested language.

## 5. How to inspect the scoring

To see the feature values directly, build the feature matrix and inspect the result:

```python
from python_pipeline.feature_matrix import build_feature_matrix
from python_pipeline.recommender import score_course_recommendations

feature_df = build_feature_matrix(
    resume_text,
    extracted_skills,
    courses_df,
    user_level="beginner",
    target_pathways=["Data Science"],
    resume_audience_terms=["analytics"],
    user_language="en",
)
scored = score_course_recommendations(feature_df)
print(scored["recommendation_score"].head())
```

## 6. Notes

- `gap_score` is intentionally inverted from similarity: lower similarity means a larger gap.
- The recommendation engine uses a weighted linear model, not a machine learning classifier.
- The history score is a small but meaningful boost, especially for users with course engagement records.

- dashboard presentation
- ideally, if its listed as a course
- history of completion for all users 
- practice exam 
- rather than top 10 it can be what should you do after this 
- 
