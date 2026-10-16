Skills Mapping Pipeline - How It Works
====================================

This project takes a resume and a course catalog, then builds a recommendation-style feature matrix that can be used for training a model or for reporting.

This repo now supports a SAS VS Code extension workflow for environments where the CAS host is only resolvable inside Viya.

TECH STACK
==========
- Frontend: React Native with Expo, targeting Android, iOS, and the web through
  React Native Web. `expo-document-picker` handles PDF/text uploads. On the web,
  the charts page is embedded in an iframe; on native platforms it uses
  `react-native-webview` when installed.
- Backend API: Python with FastAPI, served locally with Uvicorn. The API accepts
  pasted resume text, uploaded PDF/text files, and education-email engagement
  requests. CORS is enabled so the Expo web client can call the API locally.
- Data processing: pandas and NumPy load, clean, filter, join, and export course
  and engagement data. scikit-learn provides TF-IDF and related feature-scoring
  utilities; sentence-transformers provides optional semantic similarity with
  cached embeddings.
- Resume and language processing: pdfminer.six extracts PDF text, spaCy and
  NLTK support NLP-based processing, and the pipeline includes its own keyword,
  normalization, audience, and ISO 639-1 language handling.
- Reporting and handoff: matplotlib and seaborn support Python-generated
  figures. The `/charts` API endpoint serves a browser dashboard rendered with
  Plotly from the latest exported feature matrix. CSV files in `data/handoff`
  are prepared for SAS Studio and SAS Visual Analytics.
- SAS/Viya integration: SAS scripts train/export downstream models, while SWAT
  can read course data from CAS when the code runs in a SAS compute environment.
  The normal local workflow uses a downloaded CSV, so local CAS hostname
  resolution is not required.

RUNTIME FLOW
============
1. Start the FastAPI service. At startup it loads `data/EDU_PRODUCTS.csv`,
   normalizes the catalog, and keeps the prepared course data in memory.
2. Start the Expo app for web, Android, or iOS. The client sends form data to
   `/ranking` for resume recommendations or `/engagement-ranking` for
   history-based recommendations.
3. For a resume request, the API extracts text, identifies skills and audience
   information, filters active courses by language, builds one feature row per
   eligible course, calculates the weighted recommendation score, and returns
   the top courses as JSON. It also writes timestamped feature-matrix and
   unique-course CSV handoffs.
4. For an engagement request, the API filters `EDU_ENGAGEMENTS.csv` by email,
   requires at least one completed course, builds a learned-skill/pathway
   profile, excludes completed courses, and ranks eligible next courses.
5. The client displays progress, summary statistics, the recommendation list,
   and engagement details. After a successful request, it loads `/charts`; that
   endpoint reads `/feature_matrix` and renders pathway, skill-match, relevance,
   recommendation, and available history charts with Plotly.

PIPELINE FLOW OVERVIEW
======================

Resume/CV Input → Parser → Skill Extractor → Feature Matrix Builder → Recommendation Ranking
Engagement Input → Email Filter → Completed-Course Skill Profile → Recommendation Ranking

The pipeline executes in the following stages:

STAGE 1: INPUT COLLECTION
-------------------------
- Resume file: Plain text (.txt) or PDF (.pdf) format
- Course catalog: CSV file (local, SAS libref, or CAS connection URI)
- Engagement history (optional): EDU_ENGAGEMENTS.csv containing previous course enrollments

The web application exposes two recommendation actions:
- Resume/CV recommendation: requires pasted resume text or an uploaded file.
- Engagement recommendation: requires the learner's education email and at
  least one completed course in the engagement history.

These are alternative inputs. The engagement action does not silently invent
resume information when no resume is supplied. If the learner has no completed
course history, the application returns a message instructing them to submit a
resume/CV instead.

STAGE 2: RESUME PARSING (python_pipeline/parser.py)
----------------------------------------------------
Input: Raw resume text or PDF file

Process:
- PDF Extraction: If input is PDF, text is extracted using pdfminer.six
- Text Normalization: Resume text is cleaned and standardized for processing
- Date Parsing: Work history dates are parsed to extract start/end years
  - Formats supported: "YYYY-YYYY", "YYYY-Present", "Month YYYY - Month YYYY"
  - Current year is used if "Present" is detected: datetime.now().year
  - Enables duration calculations for experience level assessment
- Job Title Extraction: Identifies job titles from work history sections
  - Splits on common separators: ' at ', '@', dates, spaced dashes
  - Validates title length: 1-7 words
  - Filters for title-like patterns
- Education Extraction: Parses education section for degrees and institutions

Output: Normalized resume text, extracted job titles, education history

The normalized text is then passed to both skill extraction and feature
generation. The parser does not create a learned-course profile; that profile
belongs to the separate engagement path below.

STAGE 3: SKILL EXTRACTION (python_pipeline/skills.py)
------------------------------------------------------
Input: Parsed resume text

Process:
- Keyword Matching: Compares resume text against predefined skill keywords
  - Skills include: Python, SQL, machine learning, Tableau, AWS, project management, communication, etc.
  - Case-insensitive matching with phrase consolidation
- Optional spaCy Enhancement: Uses advanced NLP for skill phrase identification (if available)
- Audience Profile Detection: Identifies job titles, education level, and experience level from resume
  - Categorizes as: beginner, intermediate, or advanced based on extracted information
  - Extracts audience keywords (e.g., "data scientist", "engineer", "manager")

Output: List of extracted skills, audience profile with job titles and education details

STAGE 4: COURSE DATA LOADING (python_pipeline/course_data.py)
--------------------------------------------------------------
Input: Course catalog from CSV, SAS libref, or CAS connection

Process:
- Loads course metadata from data/EDU_PRODUCTS.csv or specified source
- Prepares dataframe with fields:
  - course_code, title, description
  - skills_learned, prerequisites
  - audience_level, target_pathway
  - language (ISO 639-1 code: en, es, fr, de, zh, etc.)
- Normalizes and standardizes all course fields

Output: DataFrame with course metadata, ready for feature matching

Important source-to-model mappings include:
- `PRODUCTCODE` -> `course_code`
- `COURSE_TITLE_GLOBAL` -> `title`
- `PRIMARY_LEARNING_PATH` -> `primary_pathway`
- `SKILL` or `SKILLS_LEARNED` -> `skills_learned`
- `ISACTIVE` -> `is_active`

The course preparation step splits skill text separated by commas, semicolons,
slashes, or pipes into `skills_list`. Language names and locale values are
normalized when eligibility is calculated, for example `English`, `en-US`,
and `en` all resolve to `en`.

STAGE 5: ENGAGEMENT HISTORY (Optional) (python_pipeline/feature_matrix.py)
---------------------------------------------------------------------------
Input: EDU_ENGAGEMENTS.csv (if present in data/ folder) and the learner email

Process:
- Each engagement row represents one learner's activity on one course. The
  same email is expected to occur on multiple course rows.
- Normalizes `email` and `sasemail`, then filters rows to the submitted email.
  Email is a learner filter, not a unique course key.
- Uses `ecode` or `productcode` as the course-code reference and joins it to
  EDU_PRODUCTS.csv.
- If duplicate rows describe the same course code, keeps the strongest record
  using progress and status ordering. Different course codes remain separate.
- Status evidence is weighted as: `viewed` = 0.3, `started` = 0.6, and
  `completed` = 1.0.

Output: Course DataFrame enhanced with completion history

For duplicate engagement records with the same course code, the parser keeps
one representative row after sorting by course code, progress, and status.
This prevents repeated snapshots of one course from inflating the profile,
while still preserving multiple different courses for the same email.

ENGAGEMENT PROFILE PATH
-----------------------
This optional path is an alternative to resume/CV recommendations. It does
not parse resume text or use resume job titles, education, experience level,
prerequisites, or resume semantic similarity.

For the submitted email, the system:
1. Finds all engagement rows for that learner.
2. Requires at least one completed course. Otherwise, the UI asks the learner
   to submit a resume/CV.
3. Excludes completed course codes from the next-course recommendations.
4. Looks up each engaged course in EDU_PRODUCTS.csv and collects its `SKILL`
   values and learning pathway.
5. Applies the status weight to the skills and pathways learned from each
   course, so completed courses contribute more evidence than started or
   viewed courses.
6. Scores each eligible next course using 70% course-skill coverage and 30%
   learner-skill coverage. That skill score contributes 80% of the final
   engagement score; pathway alignment contributes the remaining 20%.
  For skill scoring, each matched skill uses its accumulated evidence weight,
  capped at 1.0 so repeated activity cannot inflate that skill beyond
  completed-course strength. Course-skill coverage divides matched evidence
  by the number of candidate-course skills; learner-skill coverage divides
  matched evidence by the learner's total accumulated skill evidence.
7. Sorts by score, removes duplicate course titles, and returns the requested
   top N.

The Charts panel shows the completed courses, their pathways, and the learned
skills. The Recommendations panel shows next courses only.

ENGAGEMENT SCORING EXAMPLE
--------------------------
Suppose a learner completed Course A, started Course B, and viewed Course C.
The evidence weights are 1.0, 0.6, and 0.3 respectively. If all three courses
teach `statistics`, that skill receives combined evidence of 1.9. A skill found
only in the completed course receives stronger evidence than a skill found only
in a viewed course. In the score calculation, evidence for an individual skill
is capped at 1.0, so repeated engagement reinforces the profile but cannot make
one skill count more strongly than completed-level evidence.

For a candidate course with four skills, if three are present in the learner's
profile, its course-skill coverage is 3 / 4 = 0.75. If those three skills
represent 3 of the learner's 10 learned skills, its learner-skill coverage is
3 / 10 = 0.30. The engagement skill score is:

  0.70 * course-skill coverage + 0.30 * learner-skill coverage
  = 0.70 * 0.75 + 0.30 * 0.30
  = 0.615

The final engagement recommendation score is:

  0.80 * engagement skill score + 0.20 * pathway alignment

The result is therefore influenced by both what the course teaches and whether
its pathway matches the learner's previous course activity. A candidate with
no matching skills can still receive a small pathway score, but it should rank
below a candidate that matches the learned skill profile in the same pathway.

STAGE 6: FEATURE MATRIX GENERATION (python_pipeline/feature_matrix.py)
-----------------------------------------------------------------------
Input: Resume skills, audience profile, course catalog, feature preferences

Process:
- Skill Overlap Scoring: Calculates percentage of resume skills matching course prerequisites
- Prerequisite Matching: Evaluates fit based on resume experience level vs. course audience level
- Audience Matching: Compares extracted job titles/roles with course target audience
- Pathway Matching: Aligns resume career path with course learning pathways (if specified)
- TF-IDF Relevance: Semantic relevance between full resume text and course description
  - Uses sentence-transformer embeddings for semantic similarity
  - Results cached in .embeddings_cache directory to avoid recomputation
- Recommendation Score: Combines all features into final recommendation ranking

Output: Feature matrix with one row per course, columns for each scoring signal

RESUME/CV PROFILE PATH
----------------------
This is the default recommendation path. It uses submitted resume text or an
uploaded PDF/text file to:
- Extract current skills.
- Detect job titles, education, and audience terms.
- Compare current skills with course skills and prerequisites.
- Match requested experience level, target pathways, and language.
- Calculate TF-IDF and, when available, sentence-transformer semantic
  similarity between the resume and course descriptions.

The resume/CV path combines skill overlap, prerequisite match, audience match,
pathway match, level match, semantic relevance, history signal, and language
match into the general recommendation score. Engagement history can still be
attached for reporting and as a history signal, but it is not used to build an
email-based learner profile unless the optional engagement action is selected.
The default resume/CV weights are: skill overlap 26%, prerequisite match 16%,
audience match 10%, pathway match 12%, level match 12%, semantic relevance
10%, history signal 10%, and language match 4%.

For example, if a resume produces skill overlap 0.80, prerequisite match 0.75,
and the other feature values, the final score is the weighted sum of every
feature. Each feature is kept between 0 and 1 before weighting. The score is
not a probability; it is a ranking value where a larger value means a stronger
relative match within that request.

RESUME/CV GRADING EXAMPLE
-------------------------
Assume one eligible course receives these feature values from a resume/CV:

  skill_overlap     = 0.80
  prereq_match      = 0.75
  audience_match    = 0.90
  pathway_match     = 0.80
  level_match       = 1.00
  tfidf_score       = 0.65
  history_score     = 0.50
  language_match    = 1.00

The grade is calculated by multiplying each feature by its weight and adding
the contributions:

  (0.80 * 0.26) + (0.75 * 0.16) + (0.90 * 0.10) + (0.80 * 0.12)
  + (1.00 * 0.12) + (0.65 * 0.10) + (0.50 * 0.10) + (1.00 * 0.04)
  = 0.208 + 0.120 + 0.090 + 0.096
  + 0.120 + 0.065 + 0.050 + 0.040
  = 0.789

The course receives a recommendation grade of 0.789. A second course with a
grade of 0.850 ranks above it, while a course with 0.620 ranks below it. The
grade is not a percentage of completion, an exam mark, or a probability that
the learner will succeed. It is a normalized ranking value for comparing
eligible courses in the same request.

ENGAGEMENT GRADING EXAMPLE
--------------------------
Assume the learner's completed-course profile produces these values for a
candidate next course:

  course-skill coverage   = 0.75
  learner-skill coverage  = 0.30
  pathway alignment       = 0.80

First calculate the engagement skill grade:

  (0.75 * 0.70) + (0.30 * 0.30)
  = 0.525 + 0.090
  = 0.615

Then calculate the final engagement grade:

  (0.615 * 0.80) + (0.80 * 0.20)
  = 0.492 + 0.160
  = 0.652

That candidate receives an engagement recommendation grade of 0.652. Another
candidate may rank higher by covering more of the learner's learned skills,
matching a stronger learned pathway, or both. Completed course codes are
removed before this grade is calculated, so the learner is recommended a next
course rather than a course already completed.

STAGE 7: EXPORT WITH TIMESTAMP (python_pipeline/feature_matrix.py)
-------------------------------------------------------------------
Process:
- Timestamp Generation: Uses datetime.now().strftime("%Y%m%d_%H%M%S")
  - Format: YYYYMMDD_HHMMSS (e.g., 20260818_064613)
  - Ensures unique filename for each pipeline run
- Output Path: data/handoff/feature_matrix_YYYYMMDD_HHMMSS.csv
- Always exports both:
  - Timestamped version: feature_matrix_20260818_064613.csv (for audit trail)
  - Latest reference: feature_matrix.csv (soft overwrite for scripts)

Output: CSV file in data/handoff/ with all feature scores and course data

STAGE 8: RECOMMENDATION RANKING (python_pipeline/recommender.py)
-----------------------------------------------------------------
Input: Feature matrix with all scoring signals

Process:
- The resume/CV path aggregates its feature signals into
  `recommendation_score` using the configured weights and ranks highest first.
- The engagement path uses the completed-course skill profile and its separate
  engagement scoring formula described above.
- Both paths return at most the requested top N courses.
- Duplicate course codes and duplicate normalized titles are removed so course
  variants do not fill multiple result slots.

Output: Top N courses printed to console and available for downstream use

COURSE ELIGIBILITY AND UNIQUE COURSE COUNT
-------------------------------------------
Before either web recommendation path scores courses, the catalog is filtered:
1. `ISACTIVE` must equal `Y` after case normalization.
2. `language` must match the selected language after conversion to ISO 639-1,
   such as `english` -> `en`.
3. Only one catalog row is retained for each unique `course_code`.

`courses_considered` is the number of unique course codes left after these
filters. It is not the number of returned recommendations. For example,
`courses_considered = 3527` and `top N = 10` means 3,527 active English
course codes were eligible for scoring, and the UI displays the best 10 after
scoring and duplicate-title cleanup.

The count is calculated before excluding a learner's completed courses, so it
is a stable catalog-size measure. Completed courses are excluded later from
engagement recommendations, meaning fewer than 3,527 courses may remain as
possible next courses for a particular learner.

The eligibility sequence is:

  Raw EDU_PRODUCTS rows
    -> active rows (`ISACTIVE = Y`)
    -> selected-language rows
    -> one row per `course_code`
    -> feature/scoring calculation
    -> completed-course exclusion for engagement mode
    -> duplicate-title cleanup
    -> top N recommendations

This means `courses_considered` is not the count of unique titles and is not
the number of final cards shown. It is the number of unique active course codes
available to the scorer before learner-specific exclusions and top-N limiting.

STAGE 9: SAS/VISUAL ANALYTICS INTEGRATION (Optional)
-----------------------------------------------------
- Exported CSV can be imported into SAS Visual Analytics for dashboarding
- Can be scored using SAS models (scores imported back to feature matrix)
- Supports feedback loops for model training

### SAS scripts 01–04: end-to-end explanation

These four scripts form an optional SAS/CAS workflow that starts with the
Python-generated feature matrix, inspects and trains on it, scores courses
with a saved model, then prepares a table for SAS Visual Analytics (VA).
They are templates: update the file paths and confirm the CAS library and
model-store names match the target SAS environment before running them.

The conceptual sequence is:

```text
Python feature_matrix.csv
  -> 01_load_and_explore.sas
  -> 02_train_model.sas
  -> saved CAS analytic store (ASTORE)
  -> 03_export_scores.sas
  -> sas_scores.csv
  -> 04_prepare_va_data.sas
  -> CAS table VA_DASHBOARD for VA
```

The four scripts are separate SAS programs rather than one automatically
chained job. Run them in order, and make sure each script's output exists
before starting the next one.

#### 01 — Import and explore the feature matrix

File: [sas_scripts/01_load_and_explore.sas](../sas_scripts/01_load_and_explore.sas)

This is an initial data inspection step:

1. Declares the `mycas` CAS libref. The later statements in this script use
   the `WORK` library, so the libref is not used by the shown import and
   summary steps.
2. Imports `/path/to/feature_matrix.csv` into the temporary SAS table
   `WORK.FEATURE_MATRIX`. Replace the placeholder with the actual CSV path.
3. Runs `PROC CONTENTS` to show the table structure, column names, and types.
4. Runs `PROC MEANS` to summarize the listed numeric feature columns:
   `skill_overlap`, `gap_score`, `prereq_match`, `audience_match`,
   `pathway_match`, and `tfidf_score`.
5. Runs `PROC FREQ` to count the values of `primary_pathway`.

This script is for checking the shape and basic distributions of the input;
it does not train a model, persist a CAS table, or export recommendations.
`WORK` tables are temporary to the SAS session.

#### 02 — Train and save a forest model

File: [sas_scripts/02_train_model.sas](../sas_scripts/02_train_model.sas)

This script loads the feature CSV to CAS and trains a forest model:

1. `PROC CASUTIL` loads `/path/to/feature_matrix.csv` into the `CASUSER`
   caslib as `FEATURE_MATRIX`, replacing a table with the same name if it
   already exists.
2. `PROC FOREST` uses `skill_overlap` as the target and the following
   interval inputs: `gap_score`, `prereq_match`, `audience_match`,
   `pathway_match`, and `tfidf_score`.
3. The `SEED=12345` option makes the model's randomization reproducible for
   comparable runs.
4. The trained model is saved as `COURSE_RECOMMENDATION_MODEL` in the
   `CASUSER` caslib so the later scoring script can load it.

**Model interpretation:** the target is `skill_overlap`, so this script is
configured to predict skill overlap from the other listed features. It does
not directly train against `recommendation_score` or a learner feedback label.
The model output should therefore not be described as a trained probability
that a learner will enroll or succeed. If the intent is to predict a different
outcome, the target and training data must be changed to use an appropriate
label.

#### 03 — Score the feature rows and export results

File: [sas_scripts/03_export_scores.sas](../sas_scripts/03_export_scores.sas)

This script applies the saved analytic store (ASTORE) model to course rows:

1. Loads `COURSE_RECOMMENDATION_MODEL` from `CASUSER` into the SAS session
   as `WORK.MODEL`.
2. Scores `CASUSER.FEATURE_MATRIX` with `PROC ASTORE.SCORE`.
3. Copies `course_code`, `title`, and `primary_pathway` into the output and
   uses `course_code` as the ID variable.
4. Writes the scored rows to `WORK.SCORES`.
5. Exports `WORK.SCORES` to `/path/to/sas_scores.csv`; replace this
   placeholder with the desired output path.

The CAS feature table must exist before this script runs, typically from
script 02's load step. The saved model must also exist in the expected CAS
location. Check the score-result variable produced by the SAS release and
ASTORE model against the downstream script's expected `score` column; if
needed, explicitly map or rename the prediction output before exporting.

#### 04 — Create the Visual Analytics category and table

File: [sas_scripts/04_prepare_va_data.sas](../sas_scripts/04_prepare_va_data.sas)

This script turns the exported scores into a simple VA-friendly data set:

1. Imports `/path/to/sas_scores.csv` into `WORK.SAS_SCORES`. Update the path
   to match script 03's export location.
2. Creates `WORK.VA_DASHBOARD` by copying the scored rows and adding a
   character column named `recommendation_category`.
3. Categorizes the numeric `score` as:
   - `Strong` when `score >= 0.75`
   - `Recommended` when `0.5 <= score < 0.75`
   - `Consider` when `score < 0.5`
4. Attempts to save the result to the `CASUSER` caslib as `VA_DASHBOARD`,
   replacing a prior table with that name.

The threshold values are presentation buckets, not additional model training
or calibrated probability cutoffs. The score column needs to be numeric and
present in the imported CSV. Also verify the final `PROC CASUTIL SAVE` source
library: the script currently names `WORK` as `INCASLIB`, although
`WORK.VA_DASHBOARD` is a SAS WORK data set rather than a CAS table. If the SAS
environment does not support that source reference, first load the WORK table
into a CAS caslib and then save or promote the CAS table for VA.

#### Run-order checklist and handoff assumptions

- Generate the feature matrix with the Python pipeline before running the SAS
  scripts. The SAS scripts expect compatible feature column names and types.
- Replace every `/path/to/...` placeholder with paths accessible to the SAS
  session that executes the program; a local Windows path may not be visible
  to a remote Viya session.
- Confirm CAS is active and `CASUSER` is available to the current user.
- Run 01 to inspect the feature CSV, then 02 to load and train, 03 to score,
  and 04 to produce the VA category/table.
- Verify each intermediate artifact: `CASUSER.FEATURE_MATRIX`, the saved
  ASTORE model, `sas_scores.csv`, and `VA_DASHBOARD`.
- Keep in mind that script 02's target (`skill_overlap`) and script 04's
  score thresholds define the current example workflow; adjust them to the
  business outcome and score semantics intended for the deployed solution.

## SAS Extension Workflow (When CAS is internal-only)

When the CAS server is only reachable from inside Viya, use the SAS VS Code extension to export the CAS table to a CSV file and then run the local Python pipeline on that CSV.

### SAS Export Workflow (sas_scripts/load_course_catalog_via_sas_extension.sas)
---------------------------------------------------------------------------

Step 1: Export from CAS to CSV (Inside SAS/Viya environment)
- Connects to CAS host: sas-cas-server-shared-main-client:5570
- Creates libnames for:
  - Education (DNFS): eduprod.EDU_PRODUCTS
  - Education General (DNFS): edugen.EDU_AS_SBEP_ALL_ENGAGEMENT
- Exports to SAS work directory:
  - /tmp/EDU_PRODUCTS.csv (course catalog)
  - /tmp/EDU_ENGAGEMENTS.csv (enrollment history)

Step 2: Local Download
- Download exported CSVs from SAS Viya compute environment
- Place in local repo: 
  - data/EDU_PRODUCTS.csv
  - data/EDU_ENGAGEMENTS.csv

Step 3: Run Local Python Pipeline
```powershell
python -m python_pipeline.pipeline `
  --resume-text sample_resume.txt `
  --courses-csv "data/EDU_PRODUCTS.csv" `
  --output-dir data/handoff
```

### Data Flow with Timestamps
When you run the pipeline:
1. Input timestamp: Now + Current working directory
2. Processing timestamp: Stored in memory during execution
3. Output timestamp: YYYYMMDD_HHMMSS appended to output filename
   - Example: feature_matrix_20260818_064613.csv
   - Timestamp format: year(4), month(2), day(2), hour(2), minute(2), second(2)
4. CSV Columns include:
   - course_code, title, description
   - skills_match_score, prerequisite_match, audience_match
   - pathway_match, semantic_relevance_score
   - recommendation_score (final ranking)
    - historical_completion_status (if engagement data available)

### Why This Workflow Works
- The SAS extension executes code in the Viya environment and can access internal CAS hostnames
- Your local Python process only needs a CSV file and does not require direct CAS network access
- Network isolation is preserved while maintaining data pipeline functionality

### Alternative: Direct CAS Access (if network accessible)
If your machine has direct access to the CAS endpoint:

```powershell
python -m python_pipeline.pipeline `
  --resume-text sample_resume.txt `
  --courses-csv "cas://cisviya.sas.com:443/eduprod.EDU_PRODUCTS" `
  --cas-user "<username>" `
  --cas-password "<password>" `
  --cas-protocol https
```

Parameters:
- --cas-host: CAS server hostname
- --cas-port: CAS server port (default: 5570 for HTTP, 443 for HTTPS)
- --cas-protocol: http or https (default: http)
- --cas-authinfo: Alternative to password (use .authinfo file for secure auth)

EXECUTION MODES AND TIMESTAMPS
===============================

Mode 1: Local CSV Pipeline (Recommended for security)
------------------------------------------------------
```powershell
cd c:\Users\ad50377\Skills Mapping
python -m python_pipeline.pipeline `
  --resume-text sample_resume.txt `
  --courses-csv data/EDU_PRODUCTS.csv `
  --output-dir data/handoff `
  --user-level intermediate `
  --top-n 10
```

Output:
- Writes feature_matrix_20260818_064613.csv (unique timestamp)
- Prints top 10 recommended courses to console
- Logs execution steps with [Pipeline] prefix

Mode 2: Direct CAS Query
------------------------
```powershell
python -m python_pipeline.pipeline `
  --resume-text sample_resume.txt `
  --courses-csv "cas://cisviya.sas.com:443/eduprod.EDU_PRODUCTS" `
  --cas-protocol https `
  --cas-authinfo sas_viya_credentials
```

Mode 3: SAS Libref Access (Windows with SAS installed)
-------------------------------------------------------
```powershell
python -m python_pipeline.pipeline `
  --resume-text sample_resume.txt `
  --courses-csv "eduprod.edu_products" `
  --sas-config "sas_viya_connection"
```

PIPELINE PARAMETERS AND OPTIONS
================================

Required Arguments:
- --resume-text: Path to resume file (TXT or PDF)
- --courses-csv: Path to course CSV, SAS libref, or CAS URI

Optional Arguments:
- --output-dir: Output directory (default: data/handoff)
- --user-level: beginner | intermediate | advanced (default: beginner)
- --target-pathways: Comma-separated preferred pathways
- --top-n: Number of recommendations to display (default: 10)
- --language: ISO 639-1 language code (default: en)
  - Supported: en, es, fr, de, zh
  - Filters courses matching specified language
- --no-embedding-cache: Disable semantic similarity cache (forces recompute)

CAS Connection Parameters:
- --cas-host: CAS server hostname
- --cas-port: CAS server port number
- --cas-protocol: Connection protocol (http or https)
- --cas-user: CAS username
- --cas-password: CAS password
- --cas-authinfo: Credentials entry from .authinfo file
- --sas-config: saspy configuration name (Windows only)

DATA PIPELINE TIMELINE
======================

When you execute the pipeline, the following happens:

Time T0: User invokes pipeline command
  → Command-line arguments parsed
  → Output path generated: data/handoff/feature_matrix_YYYYMMDD_HHMMSS.csv
  → Current timestamp captured for filename

Time T0+: Resume Processing
  → Resume file loaded (TXT or PDF extraction)
  → Text normalized and parsed
  → Work dates extracted (start_year, end_year, duration calculated)
  → Job titles identified from work history
  → Skills extracted from normalized text
  → Audience profile built (job_titles, education_level, experience_level)

Time T0++: Course Data Loading
  → Course CSV loaded from local file or CAS query
  → Course metadata standardized
  → If available: EDU_ENGAGEMENTS.csv loaded for enrollment history
  → Engagement history merged with course catalog

Time T0+++: Feature Matrix Generation
  → For each course in catalog:
    - Calculate skill overlap score
    - Calculate prerequisite match (resume level vs. course audience)
    - Calculate audience alignment (job title keywords vs. course audience)
    - Calculate pathway match (if target_pathways specified)
    - Compute semantic relevance (sentence-transformer embedding similarity)
    - Aggregate into recommendation_score
  → Semantic embeddings cached for future runs
  → Rankings computed (highest score = best match)

Time T0++++: Export
  → Feature matrix CSV written to timestamped file
  → Filename format: feature_matrix_20260818_064613.csv
  → Both timestamped version and feature_matrix.csv (latest) created
  → File size: typically 100KB - 5MB depending on catalog size

CORE MODULE REFERENCE
====================

python_pipeline/pipeline.py (Main orchestrator)
- Entry point for entire pipeline
- Coordinates all stages: parsing → skills → features → export
- Handles command-line arguments and runtime configuration
- Manages output directory and file naming with timestamps

python_pipeline/parser.py (Resume processing)
- read_resume_text(): Loads TXT or PDF files
- extract_audience_profile(): Parses job titles, education, experience level
- Date parsing: Extracts work history start/end years
  - Handles "Present", "current", and full date ranges
  - Calculates years of experience using datetime.now().year

python_pipeline/skills.py (Skill extraction)
- extract_skills(): Identifies technical and professional skills
- Keyword matching: Compares resume text against skill dictionary
- Optional spaCy integration for advanced NLP
- Returns sorted list of extracted skills

python_pipeline/course_data.py (Course loading)
- load_courses(): Reads CSV, SAS libref, or CAS data source
- prepare_course_dataframe(): Normalizes course metadata
- Handles multiple data sources seamlessly
- Validates required columns and data types

python_pipeline/feature_matrix.py (Feature engineering & export)
- build_feature_matrix(): Computes scoring signals for each course
- Semantic embeddings: Uses sentence-transformer models
- Caching: Stores embeddings in .embeddings_cache for reuse
- build_and_export_features(): Exports timestamped CSV
  - Filename: feature_matrix_YYYYMMDD_HHMMSS.csv
  - Timestamp format: datetime.now().strftime("%Y%m%d_%H%M%S")
- parse_course_history(): Processes engagement data
- attach_course_history(): Merges enrollment history with courses

python_pipeline/recommender.py (Ranking)
- recommend_top_courses(): Aggregates features into final ranking
- Sorts by recommendation_score (highest = best)
- Filters previously completed courses if history available
- Outputs top N courses

OUTPUT ARTIFACTS
================

Feature Matrix CSV (data/handoff/feature_matrix_YYYYMMDD_HHMMSS.csv)
Columns:
- Identifiers: course_code, course_id, title, description
- Skill Scoring:
  - skills_in_resume: Resume skills matching course prerequisites
  - skill_overlap_score: Percentage match (0-1)
  - prerequisite_match: Experience level alignment (0-1)
- Audience Scoring:
  - audience_match: Resume job titles vs. course audience (0-1)
  - audience_keywords: Extracted audience descriptors
- Relevance Scoring:
  - semantic_relevance: TF-IDF/embedding similarity (0-1)
  - pathway_match: Alignment with target pathways (0-1 if applicable)
- Final Ranking:
  - recommendation_score: Aggregate score (0-1)
  - rank: Course position in recommendation list
- History (if available):
  - enrollment_status: completed | in_progress | not_started
  - completion_date: When course was completed (if available)

Console Output Example:
```
[Pipeline] Extracted 24 resume skills: ['python', 'sql', 'machine learning', ...]
[Pipeline] Detected job titles: ['Data Scientist', 'Analytics Engineer']
[Pipeline] Detected education: ['M.S. Computer Science']
[Pipeline] Attached 15 history rows from data/EDU_ENGAGEMENTS.csv
[Exporter] Feature matrix written → data/handoff/feature_matrix_20260818_064613.csv

[Pipeline] Top recommended courses
  course_code         title  recommendation_score
   CS-101  Python Fundamentals            0.892
   ML-201   Machine Learning Basics       0.856
   SQL-150  Advanced SQL Optimization     0.834
```

QUICK START
===========

1. Prerequisites
   ```powershell
   python -m pip install -r requirements.txt
   ```

2. Basic execution (local CSV)
   ```powershell
   python -m python_pipeline.pipeline `
     --resume-text sample_resume.txt `
     --courses-csv data/EDU_PRODUCTS.csv `
     --user-level beginner
   ```

3. With options
   ```powershell
   python -m python_pipeline.pipeline `
     --resume-text my_resume.pdf `
     --courses-csv data/EDU_PRODUCTS.csv `
     --output-dir data/handoff `
     --user-level intermediate `
     --target-pathways "Data Science,Cloud Engineering" `
     --top-n 15 `
     --language en
   ```

4. Check results
   ```powershell
   # View latest output file
   cat data/handoff/feature_matrix.csv

   # List all timestamped exports
   dir data/handoff/feature_matrix_*.csv
   ```

DEBUGGING AND LOGGING
=====================

The pipeline provides detailed logging prefixed with stage identifiers:
- [Pipeline]: Main pipeline execution
- [Parser]: Resume parsing operations
- [Skills]: Skill extraction results
- [Exporter]: Feature matrix export details
- [Recommender]: Ranking and scoring

Timestamp Generation:
- Used for output filename uniqueness
- Format: YYYYMMDD_HHMMSS (e.g., 20260818_064613)
- Captured at export time (T0++++)
- Enables audit trail of pipeline execution history

NOTES
=====

- The project is designed to work with sample data first, then with your own resume and course catalog
- PDF support works through the pdfminer.six library
- Semantic embeddings are cached in .embeddings_cache/ to avoid recomputation on subsequent runs
- If you want better skill extraction, expand the keyword list in python_pipeline/skills.py
- Engagement history (EDU_ENGAGEMENTS.csv) is optional but recommended for tracking completed courses
- Multiple runs with different resumes create separate timestamped output files for easy comparison
- Timestamp ensures reproducibility and audit trails for all analysis
