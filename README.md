# Skills Mapping Solution

A course recommendation engine. It maps a learner's resume (or prior course activity) to an active course catalog and returns a ranked list of courses. It also exports a feature matrix for SAS model training and SAS Visual Analytics reporting.

For full detail on scoring, eligibility rules and the SAS hand-off, see `COMPREHENSIVE_CODE_REFERENCE.md`, `HOW_IT_WORKS.md` and `SCORING.md` under documentation folder. 

## What it does

- Accepts pasted resume text or an uploaded PDF/TXT file.
- Parses the resume into sections and extracts skills, job titles, education and experience level.
- Loads and normalises the course catalog (`EDU_PRODUCTS.csv`), keeping active courses in the selected language, one row per course code.
- Builds one feature row per eligible course (skill overlap, prerequisites, audience, pathway, level, TF-IDF similarity, history, language).
- Ranks courses with a weighted recommendation score and returns the top N.
- Offers a second, alternative mode that recommends next courses from a learner's engagement history (education email).
- Serves everything through a FastAPI backend and an Expo (React Native / web) app, including a Plotly charts dashboard.
- Exports timestamped CSVs in `data/handoff/` for SAS Studio and SAS Visual Analytics.

## Recommendation modes

| Mode | Input | How it ranks |
|---|---|---|
| Resume/CV (default) | Resume text or file, level, target pathways, language | Weighted blend: skill overlap 26%, prerequisite match 16%, pathway 12%, level 12%, audience 10%, TF-IDF/semantic relevance 10%, history 10%, language 4% |
| Engagement | Education email plus `EDU_ENGAGEMENTS.csv` | Requires at least one completed course. Skill score = 70% course-skill coverage + 30% learner-skill coverage. Final = 80% skill score + 20% pathway alignment. Completed courses are excluded. |

The two modes are alternatives. If a learner has no completed course, the app asks them to submit a resume/CV instead.

## Project layout

| Path | Purpose |
|---|---|
| `python_pipeline/parser.py` | Resume parsing, job titles, education, experience years |
| `python_pipeline/skills.py` | Skill extraction and audience profile |
| `python_pipeline/course_data.py` | Catalog loading, column mapping, preparation |
| `python_pipeline/feature_matrix.py` | Feature matrix, engagement history, timestamped export, SAS score loader |
| `python_pipeline/recommender.py` | Scoring, deduplication, engagement recommendations |
| `python_pipeline/pipeline.py` | Command-line orchestrator |
| `api/main.py` | FastAPI service (`/ranking`, `/engagement-ranking`, `/charts`, `/feature_matrix`) |
| `mobile/App.js` | Expo app for web, Android and iOS |
| `sas_scripts/` | SAS export, model training and Visual Analytics scripts |
| `data/` | Catalog, engagement file, cache and `handoff/` outputs |
| `outputs/`, `scripts/`, `tests/` | Reports, support scripts, automated tests |
| `requirements.txt` | Python dependencies |

## Install

```bash
python -m pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

The spaCy model and `sentence-transformers` are optional. Without sentence-transformers the pipeline falls back to TF-IDF similarity.

## Data files

Copy these into `data/` in the repository root (see "Loading the data from SAS Viya"):

- `EDU_PRODUCTS.csv` (required): the course catalog.
- `EDU_ENGAGEMENTS.csv` (optional): learner activity, needed for engagement mode and the history signal.

### Catalog columns

Source columns are mapped to internal names by the loader:

| Source column | Internal name |
|---|---|
| `PRODUCTCODE` | `course_code` |
| `COURSE_TITLE_GLOBAL` | `title` |
| `PRIMARY_LEARNING_PATH` / `PRIMARY_LEARNING_PATHWAY` | `primary_pathway` |
| `SKILL` / `SKILLS_LEARNED` | `skills_learned` (split on commas, semicolons, slashes, pipes) |
| `ISACTIVE` | `is_active` (must be `Y`) |

Other fields used: short description, curriculum, prerequisites, audience, level and `language` (normalised to ISO 639-1, so `English`, `en-US` and `en` all become `en`). Missing columns get defaults.

### Engagement columns

`email` or `sasemail`, `ecode` or `productcode` (the course code), `status` (`viewed`, `started`, `completed`) and `progress`. Status weights are viewed 0.3, started 0.6, completed 1.0.

## Run locally

### 1. Batch pipeline (command line)

```bash
python -m python_pipeline.pipeline \
  --resume-text path/to/resume.txt \
  --courses-csv data/EDU_PRODUCTS.csv \
  --output-dir data/handoff \
  --user-level intermediate \
  --target-pathways "Data Science,Cloud Engineering" \
  --top-n 10 \
  --language en
```

Options: `--user-level` (`beginner` | `intermediate` | `advanced`), `--target-pathways`, `--top-n` (default 10), `--language` (default `en`), `--no-embedding-cache`.

### 2. API

```bash
cd api
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

On startup the API loads and prepares `data/EDU_PRODUCTS.csv` and keeps it in memory.

### 3. Frontend

```bash
cd mobile
npm install
npm run web
```

Activate your Python virtual environment before starting the API (for example `.venv\Scripts\Activate.ps1` on Windows PowerShell or `source .venv/bin/activate` elsewhere).

## Outputs

Each run writes to `data/handoff/`:

- `feature_matrix_YYYYMMDD_HHMMSS.csv`: timestamped copy for audit.
- `feature_matrix.csv`: latest copy, used by scripts and the `/charts` dashboard.
- `unique_courses_considered_*.csv`: the exact catalog scored.

`courses_considered` in the API response is the number of unique active course codes in the selected language, counted before learner exclusions and the top-N limit.

## Loading the data from SAS Viya

The catalog and engagement data come from SAS Viya and are loaded into the project by hand.

1. Open `sas_scripts/load_course_catalog_via_sas_extension.sas` in the SAS VS Code extension, connected to your Viya environment.
2. Run it. It starts the `casmain` CAS session, assigns the `casuser`, `eduprod` (Education (DNFS)) and `edugen` (Education - General (DNFS)) librefs, and uses `PROC EXPORT` to write `/tmp/EDU_PRODUCTS.csv` and `/tmp/EDU_ENGAGEMENTS.csv`.
3. Download both files from the compute server.
4. Manually copy them into the `data/` folder in the repository root as `data/EDU_PRODUCTS.csv` and `data/EDU_ENGAGEMENTS.csv`. The pipeline and API read from this folder and will not run well without them.
5. Run the pipeline or start the API.

The extension runs code on the SAS compute server, which can reach the internal CAS hostname, so your local Python process only needs the CSV files.

## SAS workflow

1. Import `feature_matrix.csv` into SAS Studio.
2. Train a recommender model with `sas_scripts/02_train_model.sas`.
3. Export scores and prepare Visual Analytics data with `sas_scripts/03_export_scores.sas` and `sas_scripts/04_prepare_va_data.sas`.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| No engagement recommendations | The email has no completed course, or `EDU_ENGAGEMENTS.csv` is missing from `data/`. Submit a resume/CV instead. |
| Fewer courses than expected | Only `ISACTIVE = Y` courses in the selected language are scored, one per course code. |
| Slow first request | Embeddings are being computed. They are cached in `data/cache/embeddings` for later runs. |
| Lower-quality matching | `sentence-transformers` is not installed, so TF-IDF is used. Install it for semantic similarity. |
| Pipeline or API cannot find the catalog | `EDU_PRODUCTS.csv` has not been copied into `data/` in the repository root. Re-run the SAS export and copy the file. |