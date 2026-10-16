# Skills Mapping Solution – Comprehensive Code Reference

This document explains the architecture, runtime flow, and logic of the project in this folder. It is intended as a technical reference for documentation and future maintenance.

## 1. What this solution does

This repository implements a course recommendation engine for learners. It takes:

- a resume or CV (plain text or PDF),
- optionally an education email and prior engagement history,
- a course catalog,
- user preferences such as pathway and level,

and produces a ranked set of courses that best match the learner’s skill profile, likely interests, and experience level.

The project blends:

- resume parsing and skill extraction,
- catalog normalisation and filtering,
- feature construction,
- recommendation scoring,
- a FastAPI backend for requests,
- a React Native / Expo frontend for uploads and results,
- SAS-oriented export pipelines for downstream analytics.

This is effectively a recommendation and feature-matrix system built to support both human-facing guidance and machine-learning handoff.

---

## 2. High-level system architecture

The codebase has three major layers:

1. Input/processing layer
   - [python_pipeline/parser.py](./python_pipeline/parser.py)
   - [python_pipeline/skills.py](./python_pipeline/skills.py)
   - [python_pipeline/course_data.py](./python_pipeline/course_data.py)
   - [python_pipeline/feature_matrix.py](./python_pipeline/feature_matrix.py)

2. Recommendation and ranking layer
   - [python_pipeline/recommender.py](./python_pipeline/recommender.py)
   - [python_pipeline/pipeline.py](./python_pipeline/pipeline.py)

3. Interface layer
   - [api/main.py](./api/main.py)
   - [mobile/App.js](./mobile/App.js)

At runtime, the flow is:

Resume / uploaded CV
  → normalize text
  → extract skills and audience profile
  → filter active course catalog
  → build feature matrix
  → compute recommendation score
  → return top courses to UI
  → optionally export CSVs for SAS / reporting

The project supports two recommendation modes:

- Resume-based recommendation: skill matching between resume and catalog.
- Engagement-based recommendation: inferred learning profile from prior course activity, using the learner’s edu email and engagement records.

---

## 3. Repository structure

The repository contains both operational code and generated outputs.

### Root-level folders and files

- [README.md](./README.md) – overview
- [HOW_IT_WORKS.md](./HOW_IT_WORKS.md) – narrative description of system logic
- [SCORING.md](./SCORING.md) – scoring explanation or score specification
- [requirements.txt](./requirements.txt) – Python dependencies
- [api/](./api/) – FastAPI app
- [mobile/](./mobile/) – Expo app for the UI
- [python_pipeline/](./python_pipeline/) – core data and ranking logic
- [data/](./data/) – course and engagement source files and generated handoff outputs
- [outputs/](./outputs/) – output artifacts or visual reports
- [scripts/](./scripts/) – support scripts
- [sas_scripts/](./sas_scripts/) – SAS workflow scripts
- [tests/](./tests/) – automated tests

### Key code files

- [python_pipeline/parser.py](./python_pipeline/parser.py) – resume parsing and extraction
- [python_pipeline/skills.py](./python_pipeline/skills.py) – skill detection and normalization
- [python_pipeline/course_data.py](./python_pipeline/course_data.py) – course catalog load and cleaning
- [python_pipeline/feature_matrix.py](./python_pipeline/feature_matrix.py) – vector and similarity feature engineering
- [python_pipeline/recommender.py](./python_pipeline/recommender.py) – final ranking logic
- [python_pipeline/pipeline.py](./python_pipeline/pipeline.py) – CLI orchestrator
- [api/main.py](./api/main.py) – HTTP API and upload handlers
- [mobile/App.js](./mobile/App.js) – mobile web app UI

---

## 4. Technical stack

### Python stack

The backend is built with:

- FastAPI for the HTTP API
- pandas for dataframe-based transformations
- NumPy for vectorized computations
- scikit-learn for TF-IDF and cosine similarity
- sentence-transformers for semantic encoding (optional but preferred)
- pdfminer.six for PDF text extraction
- spaCy and NLTK-style NLP heuristics for resume enrichment
- matplotlib / seaborn / Plotly for charts and report generation

### Frontend stack

The app in [mobile/App.js](./mobile/App.js) is built with:

- React Native
- Expo
- expo-document-picker for PDF/text uploads
- react-native-webview on native platforms when available
- React Native Web support so the same app runs in a browser

### Integration points

The project also includes SAS/Viya integration support via:

- CAS and SAS libref loading patterns,
- CSV handoff to SAS Studio / Visual Analytics,
- scripts under [sas_scripts/](./sas_scripts/)

This allows the project to act as a data preparation and recommendation layer before SAS model training or reporting.

---

## 5. Data model and core inputs

### 5.1 Resume input

The solution accepts either:

- resume text pasted directly into the web form, or
- a PDF or .txt file uploaded through the mobile app or API.

The resume is normalized by stripping repeated whitespace and line-end variants and then processed into sections such as:

- summary
- experience
- work experience
- education
- skills
- technical skills
- projects

The parser tries to identify the most important structured parts of a CV, which is useful for both extracting skills and detecting a learner profile.

### 5.2 Course catalog input

The main course data is expected to be a CSV with fields like:

- `course_code`
- `title`
- `short_desc`
- `curriculum`
- `primary_learning_pathway`
- `level`
- `skills_learned`
- `prerequisites`
- `audience`
- `language`
- `is_active`

The loader in [python_pipeline/course_data.py](./python_pipeline/course_data.py) normalizes column names in a tolerant way so that a real product catalog can be mapped to the internal structure with minimal friction.

### 5.3 Engagement history input

For engagement-based recommendations, the application reads historical course activity from a CSV containing fields such as:

- `email`
- `sasemail`
- `course_code` or `ecode`/`productcode`
- `status`
- `progress` or `history_progress`

This is used to infer what the learner has already viewed, started, or completed so the system can recommend the next best courses instead of repeating already-visited material.

---

## 6. Parsing and normalization logic

### [python_pipeline/parser.py](./python_pipeline/parser.py)

This file does the first conversion from unstructured resume text into searchable structured data.

#### Main responsibilities

- `normalize_text()`
  - converts CRLF to LF
  - normalizes tabs and repeated spaces
  - trims whitespace

- `read_resume_text(path)`
  - reads plain text or extracts text from a PDF using `pdfminer`

- `extract_resume_sections(text)`
  - looks for section headers such as `Experience`, `Education`, `Skills`
  - splits the resume into sections for targeted parsing

- `extract_job_titles(text)`
  - scans likely work experience sections
  - tries to identify likely titles using regex patterns and common seniority keywords
  - removes noise such as bullet actions and company markers

- `extract_education(text)`
  - collects educational entries from degree and institution-related lines

- `extract_experience_years(text)`
  - identifies experience ranges and converts them into estimated years

This parser does not try to be a full NLP extraction engine; it is a practical heuristic parser tuned for resume-like documents and enterprise training contexts.

---

## 7. Skill extraction logic

### [python_pipeline/skills.py](./python_pipeline/skills.py)

This module is responsible for producing a canonical set of skills from the resume.

#### Core design

The logic uses a hybrid approach:

1. Keyword dictionary matching
2. Resume section scanning
3. Optional spaCy noun-entity and chunk analysis

#### Keyword dictionary

The project maintains a curated list of keywords and phrases such as:

- Python
- SQL
- SAS
- Tableau
- Power BI
- AWS
- machine learning
- data engineering
- project management
- communication
- leadership
- cloud
- ETL
- NLP

The `default_skill_keywords()` function creates a long list of candidate skill entries that reflect the training catalog and enterprise skill vocabulary.

#### How matching works

The helper function `_keyword_matches()`:

- normalizes both the resume text and skill phrases,
- strips punctuation,
- uses regex word boundaries,
- collects matches in a set to avoid duplicates.

The function then checks both the full resume text and recognized resume sections such as `skills` or `technical skills`.

#### Why this is useful

It lets the project build a skill set from a CV even when the resume is not extremely standardized. This skill set becomes the basis for:

- course scoring,
- audience context,
- pathway alignment,
- resume-to-catalog similarity.

---

## 8. Course catalog preparation logic

### [python_pipeline/course_data.py](./python_pipeline/course_data.py)

This module loads and prepares the course catalog so it can be compared against a learner profile.

#### `load_courses()`

This function:

- looks for a CSV in `data/` if no explicit path is passed,
- reads the catalog using pandas,
- normalizes column names by mapping common variants to canonical names,
- fills missing required columns with sensible defaults.

Examples of canonical mappings include:

- `PRODUCTCODE` → `course_code`
- `COURSE_TITLE_GLOBAL` → `title`
- `PRIMARY_LEARNING_PATHWAY` → `primary_learning_pathway`
- `SKILLS_LEARNED` → `skills_learned`
- `PREREQUISITES` → `prerequisites`
- `ISACTIVE` → `is_active`

#### `prepare_course_dataframe()`

This function transforms raw course catalog rows into a recommendation-friendly dataset.

It:

- fills missing fields,
- normalizes `is_active`,
- splits skill text by delimiters such as commas, semicolons, pipes, and slashes,
- creates `skills_list`,
- creates `combined_text`, which concatenates title, short description, curriculum, skills, and level,
- renames `primary_learning_pathway` to `primary_pathway` for downstream usage.

This `combined_text` column is critical because it supports both TF-IDF and semantic encoding.

#### `export_unique_courses_considered()`

This function filters the catalog to only:

- active courses,
- matching language,
- deduplicated by course code,
- exported as a CSV handoff file.

This export acts as a record of the exact catalog viewed for recommendation and is used in the handoff workflow to SAS and reporting tools.

---

## 9. Feature matrix generation

### [python_pipeline/feature_matrix.py](./python_pipeline/feature_matrix.py)

This is the central analytical piece of the solution. It creates one feature row per course and computes values used in ranking.

#### Why the system needs a feature matrix

A resume is not directly comparable to a catalog unless it is translated into a common representation. The system builds a feature matrix where each row is a course and each column is a measurable match signal.

The generated features include:

- `skill_overlap`
- `gap_score`
- `prereq_match`
- `audience_match`
- `level_match`
- `pathway_match`
- `tfidf_score`
- `language_match`
- `history_score`

#### Key helper functions

- `_get_course_tfidf()`
  - builds a TF-IDF model over the course corpus

- `_course_corpus_hash()`
  - creates a stable hash of the course dataset so embedding caches can be invalidated if the catalog changes

- `_get_sentence_model()`
  - lazily loads a SentenceTransformer model

- `_get_course_embeddings()`
  - caches embeddings in memory and optionally on disk at `data/cache/embeddings`

- `_to_iso639_1()`
  - converts language labels like `English`, `en-US`, `zh_CN`, `fr` into normalized ISO codes such as `en`, `zh`, `fr`

#### Resume-to-course similarity pipeline

The feature generation function `build_feature_matrix()` executes these steps:

1. Compute the resume skill set and audience tokens.
2. Derive course skill lists from the catalog if the raw `skills_list` is empty.
3. Compute `skill_overlap` as a ratio of course skills matched against resume skills.
4. Compute `tfidf_score` using scikit-learn TF-IDF cosine similarity.
5. Compute semantic `gap_score` using SentenceTransformer embeddings and cosine similarity.
6. Compute `prereq_match` by comparing the resume skills against prerequisite vocabulary.
7. Compute `audience_match` by checking overlap between resume audience terms and course audience descriptors.
8. Compute `level_match` by comparing the requested learner level to the course’s level.
9. Compute `pathway_match` by checking whether the course pathway aligns with the learner’s target pathways or contextual resume terms.
10. Compute `language_match` through ISO normalization.
11. Compute `history_score` based on prior engagement data.

This creates a balanced feature vector for each course, allowing the recommender to weigh both hard and soft signals.

#### Semantic similarity approach

The project uses both classic lexical similarity and embedding similarity:

- TF-IDF is good for exact or high-frequency keyword overlap.
- SentenceTransformer embeddings capture deeper semantic similarity even without exact wording overlap.

This is especially useful when a learner’s CV says “natural language processing” while the course catalog says “text analytics” or “AI literacy.”

---

## 10. Recommendation scoring logic

### [python_pipeline/recommender.py](./python_pipeline/recommender.py)

This module turns the feature matrix into the final ranked list of courses.

#### Weighted score formula

`score_course_recommendations()` uses these weights by default:

- skill_overlap: 0.26
- prereq_match: 0.16
- audience_match: 0.10
- pathway_match: 0.12
- level_match: 0.12
- tfidf_score: 0.10
- history_score: 0.10
- language_match: 0.04

The total recommendation score is therefore:

`recommendation_score = 0.26*skill_overlap + 0.16*prereq_match + 0.10*audience_match + 0.12*pathway_match + 0.12*level_match + 0.10*tfidf_score + 0.10*history_score + 0.04*language_match`

This ensures skill alignment is the strongest factor, while prerequisites, level, pathway, and language still contribute meaningfully.

#### Why the score is structured this way

- `skill_overlap` is treated as the strongest direct signal because it measures similarity between the learner and the course.
- `prereq_match` prevents the system from over-recommending courses that the learner has not built the necessary foundation for.
- `level_match` helps avoid recommending courses that are too advanced or too introductory.
- `pathway_match` allows preferences or target pathways to influence the ranking.
- `history_score` allows past engagement to influence the next suggestion, especially for continuing learners.

#### Deduplication logic

`_dedupe_by_title()` normalizes course titles and removes duplicates where the same course appears under multiple catalog variants or formatting differences.

This helps avoid repeated recommendations for near-identical courses like live vs. recorded versions or alternate encoding variants.

#### Engagement-based recommendation

`recommend_from_engagement()` builds a profile from a learner’s completed, started, and viewed courses.

It:

- maps each engagement record to a status weight (`completed` > `started` > `viewed`),
- aggregates learned skills and primary pathways,
- excludes courses already completed,
- computes a skill overlap between the learner’s actual history and each candidate course,
- calculates a `prerequisite_match` from prerequisite text, if present,
- ranks the remaining courses by a weighted score.

This is valuable for recommending the next course in a pathway instead of rehashing a generic search.

---

## 11. CLI orchestration

### [python_pipeline/pipeline.py](./python_pipeline/pipeline.py)

This file is the main command-line entry point used to build a feature matrix from a resume and a course catalog.

It accepts arguments such as:

- `--resume-text`
- `--courses-csv`
- `--output-dir`
- `--user-level`
- `--target-pathways`
- `--top-n`
- `--language`
- optional CAS/SAS connection settings

#### Runtime flow in `main()`

1. Reads the resume document.
2. Loads the course catalog.
3. Prepares the catalog for ranking.
4. Exports the unique course list considered.
5. Extracts resume skills and audience profile.
6. Builds the feature matrix.
7. Exports the matrix as CSV.
8. Ranks the results and prints the top N.

This script is the clearest example of the full pipeline operating as a batch recommendation job.

---

## 12. API layer and HTTP behavior

### [api/main.py](./api/main.py)

This is the FastAPI API that exposes the recommendation logic to the frontend and automation clients.

#### App startup

On startup, the app attempts to:

- resolve the Primary course CSV,
- load the catalog,
- prepare it in memory,
- cache it globally as `COURSES_CACHE`.

This reduces repeated work across requests.

#### `/_eligible_courses()`

This function filters the catalog to:

- active courses only,
- requested language,
- one row per `course_code`.

This is important for eliminating duplicate variants and enforcing the selected language requirement.

#### `/ranking`

This POST endpoint accepts:

- `resume_text`
- `resume_file`
- `edu_email`
- `user_level`
- `target_pathways`
- `course_csv`
- `top_n`
- `language`

This endpoint handles both text and file uploads.

For uploaded PDFs:

- reads the bytes,
- extracts text with `pdfminer`
- normalizes the content,
- rejects empty or unsupported input.

It then:

- loads the catalog,
- prepares the feature matrix,
- optionally attaches engagement history,
- runs recommendation scoring,
- returns the top courses via JSON.

The endpoint also writes CSV handoff files to `data/handoff` such as:

- `unique_courses_considered_*.csv`
- feature matrix exports for downstream analytics

#### Engagement mode

The API also checks whether `EDU_ENGAGEMENTS.csv` exists and loads it when present. It then:

- filters for the learner email,
- computes a profile of viewed/started/completed courses,
- attaches that history to the course DataFrame,
- generates a separate engagement recommendation profile.

This allows the system to give learners “next best course” suggestions based on historical learning behavior rather than only a fresh resume.

---

## 13. Frontend application behavior

### [mobile/App.js](./mobile/App.js)

The frontend is a single-screen dashboard designed for a user to:

- paste resume text,
- upload PDF/TXT resume files,
- set their level and target pathways,
- optionally provide a learner email for engagement-based suggestions,
- review recommendation results,
- refresh charts.

#### Key React state

The app maintains:

- `resumeText`
- `userLevel`
- `targetPathways`
- `eduEmail`
- `language`
- `loading`
- `statusMessage`
- `progressSteps`
- `results`
- `error`
- `chartsKey`
- `lastUpdated`

This state controls the UI flow and supports the “working / ready / error” experience.

#### Upload flow

When choosing a file:

- the app opens the DocumentPicker,
- posts the file as `multipart/form-data`,
- includes `user_level`, `target_pathways`, `top_n`, `language`, and optional email,
- sends the request to `/ranking`.

On web, the app reads the chosen file as a blob and converts it to a `File` object. On native, it sends the local file URI in the form payload.

#### Text submission flow

The text-based path is similar but simpler:

- reads the textarea input,
- forms a payload with `resume_text`,
- sends it to `/ranking`.

#### Engagement path

The `submitEngagement()` flow:

- requires an education email,
- sends the email to `/engagement-ranking`,
- expects candidate courses informed by the learner history profile.

#### Results rendering

Once the backend responds:

- `results` is stored,
- `progressSteps` records the request lifecycle,
- the charts panel refreshes via `chartsKey` to trigger a new backend chart view.

The app renders:

- stat summary cards,
- recommendation cards with code/title/score,
- a chart panel with live dashboard content,
- a progress log for backend request tracking.

The charts are displayed via the `/charts` endpoint, which is loaded either as an iframe on web or WebView content on native devices.

---

## 14. Recommendation output contract

The backend returns structured JSON containing a recommendation payload. In practice, the response includes:

- a `mode` (resume or engagement),
- `courses_considered`,
- `recommendations`,
- optional `engagement_profile`,
- optional `history_summary`,
- optional `progress` entries describing pipeline stages.

Each recommendation item typically includes:

- `course_code`
- `title`
- `primary_pathway`
- `recommendation_score`
- `skill_overlap`
- `prereq_match`
- `audience_match`
- `pathway_match`
- `level_match`
- `tfidf_score`
- `language`
- `language_match`
- `history_score`

This makes the data suitable for UI rendering and for downstream model training or human review.

---

## 15. How the project produces a SAS / analytics-ready handoff

The solution is designed to produce handoff files for SAS Studio and SAS Visual Analytics.

#### `export_unique_courses_considered()`

Exports the filtered, language-aware, deduplicated course list.

#### `build_and_export_features()`

Writes a full feature matrix CSV consisting of the per-course features and scoring signals.

#### SAS workflow integration

The repository includes scripts under [sas_scripts/](./sas_scripts/) for:

- training a model on the exported feature matrix,
- exporting model scores,
- preparing VA data for dashboards and reporting.

For a script-by-script explanation of `01_load_and_explore.sas` through
`04_prepare_va_data.sas`, including their inputs, outputs, run order, and
important configuration assumptions, see
[HOW_IT_WORKS.md — SAS scripts 01–04](./HOW_IT_WORKS.md#sas-scripts-01-04-end-to-end-explanation).

This design separates:

- data preparation and recommendation scoring (Python),
- advanced model training and visual analytics (SAS),
- front-end presentation (React Native / web).

---

## 16. Performance and design considerations

The solution contains several features meant to reduce repeated expensive work:

### In-memory caching

The feature matrix and sentence model are cached in memory within one process.

This avoids reloading a model and re-encoding the same catalog if the same request path repeatedly calls the recommender logic.

### Disk embedding cache

The embedding model caches vectors as `.npy` files in `data/cache/embeddings` using a content hash of the course catalog.

This means if the course corpus is unchanged, later runs can skip re-encoding the full catalog.

### Deduplication of course variants

Course variants with different codes but similar or identical titles are collapsed in ranking to avoid noisy duplicates.

### Language normalization

The code normalizes language names and locale tags before comparison. This reduces mismatch problems like:

- `English` vs `en`
- `en-US` vs `en`
- `zh_CN` vs `zh`

---

## 17. Important implementation details and conventions

### 17.1 Case-insensitive normalization

Most matching logic is case-insensitive and strips punctuation before comparing strings.

This is especially important in:

- skill recognition,
- course title deduplication,
- language mapping,
- course history normalization.

### 17.2 Fallback behavior

The project intentionally degrades gracefully:

- if `sentence-transformers` is missing, it falls back to TF-IDF,
- if a catalog column is missing, it creates a default placeholder,
- if engagement history is missing, it still works with resume-based scoring,
- if `language` is unknown, it defaults to `en`.

### 17.3 Data cleaning is heuristic-driven

The project does not rely on an industrial-grade ontology or strict schema beyond what is practical in the dataset. Instead, it uses:

- regex-driven extraction,
- normalization patterns,
- keyword dictionaries,
- course metadata similarity,
- flexible column mapping.

This is appropriate for a business-facing recommendation system that must work with messy resume and catalog data.

---

## 18. Typical runtime flow from user perspective

A normal user journey looks like this:

1. Open the Expo app in the browser or mobile device.
2. Paste resume text or upload a PDF / TXT file.
3. Set user level and target pathways if needed.
4. Press “Submit Text” or “Upload PDF/Text”.
5. The frontend sends a POST request to `/ranking`.
6. The FastAPI backend loads the course catalog and resume text.
7. Resume sections are extracted and skills are identified.
8. A feature matrix is built for every course.
9. Courses are scored using weighted factors.
10. The top N course matches are returned to the frontend.
11. The UI renders the recommendations and updates the charts panel.
12. CSV exports are created for analytics handoff.

---

## 19. Main extension points for future enhancement

If this solution is extended, the most natural areas are:

### Better resume parsing

- Add more section detection headers.
- Add semantic extraction for certifications and competencies.
- Add optional entity extraction with a larger NLP model.

### Better skill ontology

- Expand the skill dictionary to enterprise-specific competencies.
- Add synonyms and alias handling across product families.

### Improved course modeling

- Add richer metadata fields such as learning outcomes and duration.
- Add learner profile tags and course delivery preference metadata.

### Advanced ranking

- Add user behavior learning from historical click-through or completion rates.
- Add personalized ranking based on prior course history or team role.
- Add a supervised model on top of the feature matrix.

### Visualization

- Add new charts using Plotly or a dashboard library.
- Provide downloadable HTML reports.

---

## 20. Summary

This project is a practical recommendation system for mapping learner capability to course offerings. It combines:

- heuristic resume parsing,
- course catalog normalization,
- semantic and lexical matching,
- weighted ranking,
- data export for SAS / analytics workflows,
- a user-friendly frontend and FastAPI endpoint layer.

The code is structured around a clean separation of concerns:

- parsing logic in [python_pipeline/parser.py](./python_pipeline/parser.py)
- skill extraction in [python_pipeline/skills.py](./python_pipeline/skills.py)
- catalog preparation in [python_pipeline/course_data.py](./python_pipeline/course_data.py)
- feature engineering in [python_pipeline/feature_matrix.py](./python_pipeline/feature_matrix.py)
- final ranking in [python_pipeline/recommender.py](./python_pipeline/recommender.py)
- HTTP API in [api/main.py](./api/main.py)
- user experience in [mobile/App.js](./mobile/App.js)

This means the project is easy to reason about, extend, test, and adapt to new course catalogs or different recommendation strategies.

---

## 21. Quick start references

For anyone working with this repo, the most important operational commands are:

### Run the pipeline locally

```bash
python -m python_pipeline.pipeline \
  --resume-text sample_resume.txt \
  --courses-csv data/EDU_PRODUCTS.csv \
  --output-dir data/handoff
```

### Run the API

```bash
cd api
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Run the frontend

```bash
cd mobile
npm install
npm run web
```

This is the complete lifecycle: resume input → processing → scoring → export → frontend display.
