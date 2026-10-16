import io
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import HTMLResponse
import pandas as pd
from fastapi import Response

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from python_pipeline.course_data import load_courses, prepare_course_dataframe, export_unique_courses_considered
from python_pipeline.feature_matrix import (
    build_feature_matrix,
    build_and_export_features,
    parse_course_history,
    attach_course_history,
    _to_iso639_1,
)
from python_pipeline.parser import normalize_text, extract_audience_profile
from python_pipeline.recommender import recommend_from_engagement, recommend_top_courses, score_course_recommendations
from python_pipeline.skills import extract_skills

app = FastAPI(
    title="Skills Mapping Recommendation API",
    description="Upload a resume PDF or paste text to receive ranked course recommendations.",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

COURSES_CACHE = None


def _eligible_courses(courses_df: pd.DataFrame, language: str = "en") -> tuple[pd.DataFrame, int]:
    """Keep active courses in the requested language, one row per code."""
    eligible = courses_df.copy()
    eligible = eligible[eligible["is_active"].eq("Y")]
    requested_language = _to_iso639_1(language)
    course_language = eligible["language"].apply(_to_iso639_1) if "language" in eligible.columns else pd.Series("en", index=eligible.index)
    eligible = eligible[course_language.eq(requested_language)]
    eligible = eligible.drop_duplicates(subset=["course_code"], keep="first")
    eligible["language"] = requested_language
    return eligible.reset_index(drop=True), int(eligible["course_code"].nunique())

@app.on_event("startup")
async def startup_event():
    global COURSES_CACHE
    try:
        courses_path = _resolve_course_csv()
        courses_df = load_courses(courses_path)
        COURSES_CACHE = prepare_course_dataframe(courses_df)
        print(f"[Startup] Loaded course catalog with {len(COURSES_CACHE)} rows.")
    except Exception as exc:
        print(f"[Startup] Failed to load course catalog: {exc}")


def _resolve_course_csv(csv_path: Optional[str] = None) -> Path:
    if csv_path:
        path = Path(csv_path)
        if not path.is_file():
            raise FileNotFoundError(f"Course catalog CSV not found: {path}")
        return path

    default_path = ROOT_DIR / "data" / "EDU_PRODUCTS.csv"
    if default_path.exists():
        return default_path

    data_dir = ROOT_DIR / "data"
    if not data_dir.exists():
        raise FileNotFoundError("No course catalog provided and data/ directory is missing.")

    csv_files = [p for p in data_dir.glob("*.csv") if p.is_file()]
    if len(csv_files) == 1:
        return csv_files[0]
    if len(csv_files) == 0:
        raise FileNotFoundError("No CSV files found in data/ and no courses_csv provided.")

    raise FileNotFoundError(
        "Multiple CSV files found in data/. Pass courses_csv explicitly to select the course catalog."
    )


def _read_uploaded_resume(upload: UploadFile) -> str:
    filename = upload.filename or "resume"
    suffix = Path(filename).suffix.lower()
    content = upload.file.read()
    if suffix == ".pdf":
        try:
            from pdfminer.high_level import extract_text

            text = extract_text(io.BytesIO(content))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"PDF parsing failed: {exc}")
    elif suffix in {".txt", ".md", ""}:
        try:
            text = content.decode("utf-8", errors="ignore")
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Text decoding failed: {exc}")
    else:
        raise HTTPException(status_code=400, detail="Unsupported file type. Use .pdf or .txt.")

    normalized = normalize_text(text)
    if not normalized:
        raise HTTPException(status_code=400, detail="Uploaded resume is empty after parsing.")
    return normalized


@app.post("/ranking")
async def ranking(
    resume_text: Optional[str] = Form(None),
    resume_file: Optional[UploadFile] = File(None),
    edu_email: Optional[str] = Form(None),
    user_level: str = Form("beginner"),
    target_pathways: Optional[str] = Form(None),
    top_n: int = Form(10),
    courses_csv: Optional[str] = Form(None),
    language: str = Form("en"),
):
    print("RANKING request received", "resume_file=" + str(resume_file.filename) if resume_file else "resume_text provided")
    if resume_file is None and not resume_text:
        raise HTTPException(status_code=400, detail="Provide resume_text or resume_file.")

    if resume_file is not None:
        print("Reading uploaded resume file", resume_file.filename)
        resume_text = _read_uploaded_resume(resume_file)
        print("Uploaded resume parsed, length", len(resume_text))
    else:
        resume_text = normalize_text(resume_text)
        print("Normalized resume text, length", len(resume_text))

    if not resume_text.strip():
        raise HTTPException(status_code=400, detail="Resume text cannot be empty.")

    try:
        if courses_csv:
            courses_path = _resolve_course_csv(courses_csv)
            courses_df = load_courses(courses_path)
            courses_df = prepare_course_dataframe(courses_df)
        else:
            global COURSES_CACHE
            if COURSES_CACHE is None:
                courses_path = _resolve_course_csv()
                courses_df = load_courses(courses_path)
                COURSES_CACHE = prepare_course_dataframe(courses_df)
            courses_df = COURSES_CACHE
        courses_df, courses_considered = _eligible_courses(courses_df, language)

        unique_courses_export_path = ROOT_DIR / "data" / "handoff" / f"unique_courses_considered_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        unique_course_df = export_unique_courses_considered(courses_df, language=language, output_path=unique_courses_export_path)
        print(f"[Exporter] Unique courses considered written → {unique_courses_export_path}")
        print(f"[Exporter] {len(unique_course_df)} unique considered courses exported")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load courses: {exc}")

    history_summary = None
    history_path = ROOT_DIR / "data" / "EDU_ENGAGEMENTS.csv"
    if history_path.exists():
        try:
            with history_path.open("rb") as fh:
                history_df = parse_course_history(fh)
            if not history_df.empty:
                courses_df = attach_course_history(courses_df, history_df)
                history_summary = {
                    "unique_courses": int(history_df["course_code"].nunique()),
                    "completed_count": int((history_df["history_action"] == "completed").sum()),
                    "started_count": int((history_df["history_action"] == "started").sum()),
                    "viewed_count": int((history_df["history_action"] == "viewed").sum()),
                    "top_completed_courses": history_df[
                        history_df["history_action"] == "completed"
                    ].sort_values(["history_progress", "course_code"], ascending=[False, True])
                    .head(10)[["course_code", "history_progress"]]
                    .to_dict(orient="records"),
                }
        except Exception:
            history_summary = None

    def stage(name: str):
        return {
            "name": name,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    progress = [stage("start")]

    target_pathways_list = [p.strip() for p in (target_pathways or "").split(",") if p.strip()] or None

    try:
        extracted_skills = extract_skills(resume_text)
        progress.append(stage("skills_extracted"))

        audience_profile = extract_audience_profile(resume_text)
        progress.append(stage("audience_profile_extracted"))

        feature_df = build_feature_matrix(
            resume_text=resume_text,
            extracted_skills=extracted_skills,
            courses_df=courses_df,
            user_level=user_level,
            target_pathways=target_pathways_list,
            resume_audience_terms=audience_profile["audience_terms"],
            user_language=language,
        )
        progress.append(stage("feature_matrix_built"))

        feature_export_path = build_and_export_features(
            resume_text=resume_text,
            extracted_skills=extracted_skills,
            courses_df=courses_df,
            user_level=user_level,
            target_pathways=target_pathways_list,
            resume_audience_terms=audience_profile["audience_terms"],
            output_path=ROOT_DIR / "data" / "handoff" / f"feature_matrix_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv",
            feature_df=feature_df,
            user_language=language,
        )
        progress.append(stage("feature_matrix_exported"))

        ranked = recommend_top_courses(feature_df, top_n=top_n)
        progress.append(stage("courses_ranked"))

        # The exported feature matrix CSV (read by /feature_matrix and the
        # /charts dashboard) was written *before* recommendation_score was
        # computed, and covers the whole catalog rather than the deduped
        # top_n list. Without this, the "most relevant courses" chart ranks
        # by a different formula (raw tfidf_score) over a different set of
        # rows than what's actually shown in the Recommendations panel.
        # Patch the same CSV in place so both views agree.
        try:
            export_df = pd.read_csv(feature_export_path)
            scored_export_df = score_course_recommendations(export_df)
            recommended_codes = set(ranked["course_code"].astype(str))
            scored_export_df["is_recommended"] = (
                scored_export_df["course_code"].astype(str).isin(recommended_codes)
            )
            scored_export_df.to_csv(feature_export_path, index=False)
        except Exception as exc:
            print(f"[Ranking] Failed to annotate feature matrix export: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Ranking failed: {exc}")

    results = []
    for _, row in ranked.iterrows():
        results.append(
            {
                "course_code": str(row.get("course_code", "")),
                "title": str(row.get("title", "")),
                "primary_pathway": str(row.get("primary_pathway", "")),
                "recommendation_score": float(row.get("recommendation_score", 0.0)),
                "skill_overlap": float(row.get("skill_overlap", 0.0)),
                "prereq_match": float(row.get("prereq_match", 0.0)),
                "audience_match": float(row.get("audience_match", 0.0)),
                "pathway_match": float(row.get("pathway_match", 0.0)),
                "level_match": float(row.get("level_match", 0.0)),
                "tfidf_score": float(row.get("tfidf_score", 0.0)),
                "history_score": float(row.get("history_score", 0.0)),
                "language": str(row.get("language", "")),
                "language_match": float(row.get("language_match", 0.0)),
            }
        )

    payload = {
        "top_n": top_n,
        "courses_considered": courses_considered,
        "user_level": user_level,
        "target_pathways": target_pathways or "",
        "language": language,
        "edu_email": edu_email or "",
        "history_summary": history_summary or {},
        "extracted_skills": extracted_skills,
        "audience_profile": audience_profile,
        "recommendations": results,
        "progress": progress,
    }
    return JSONResponse(content=payload)


@app.post("/engagement-ranking")
async def engagement_ranking(
    edu_email: str = Form(...),
    top_n: int = Form(10),
    language: str = Form("en"),
):
    email = edu_email.strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Enter an education email to use engagement history.")

    history_path = ROOT_DIR / "data" / "EDU_ENGAGEMENTS.csv"
    if not history_path.exists():
        raise HTTPException(status_code=404, detail="Engagement history is not available.")
    try:
        with history_path.open("rb") as fh:
            history_df = parse_course_history(fh, email=email)
        if history_df.empty:
            raise HTTPException(status_code=404, detail="No engagement history found for that email.")
        completed_count = int((history_df["history_action"] == "completed").sum())
        if completed_count == 0:
            raise HTTPException(
                status_code=422,
                detail="No completed courses found for that email. Submit a resume to get recommendations.",
            )
        courses_df = COURSES_CACHE
        if courses_df is None:
            courses_df = prepare_course_dataframe(load_courses(_resolve_course_csv()))
        courses_df, courses_considered = _eligible_courses(courses_df, language)
        ranked, engagement_profile = recommend_from_engagement(courses_df, history_df, top_n=top_n)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Engagement recommendation failed: {exc}")

    return JSONResponse(content={
        "top_n": top_n,
        "courses_considered": courses_considered,
        "edu_email": email,
        "mode": "engagement",
        "engagement_profile": engagement_profile,
        "history_summary": {
            "unique_courses": int(history_df["course_code"].nunique()),
            "completed_count": completed_count,
            "started_count": int((history_df["history_action"] == "started").sum()),
            "viewed_count": int((history_df["history_action"] == "viewed").sum()),
        },
        "recommendations": ranked.to_dict(orient="records"),
        "progress": [{"name": "engagement_profile_built", "timestamp": datetime.utcnow().isoformat() + "Z"}],
    })


@app.get("/")
async def root():
    return {
        "service": "Skills Mapping Recommendation API",
        "status": "ok",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/feature_matrix")
async def feature_matrix():
    try:
        handoff_dir = ROOT_DIR / "data" / "handoff"
        if not handoff_dir.exists():
            return JSONResponse(content={"error": "No handoff directory found"}, status_code=404)

        csv_files = sorted(handoff_dir.glob("feature_matrix_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not csv_files:
            return JSONResponse(content={"error": "No feature matrix CSV files found"}, status_code=404)

        fm_path = csv_files[0]
        df = pd.read_csv(fm_path)
        records = df.fillna("").to_dict(orient="records")
        return JSONResponse(content={"rows": records, "source_file": str(fm_path.name)})
    except Exception as exc:
        return JSONResponse(content={"error": str(exc)}, status_code=500)


@app.get("/charts")
async def charts():
    # Plain-language dashboard that fetches /feature_matrix and renders
    # easy-to-read charts (Plotly) with explanations, not raw column names.
    html = """
<!doctype html>
<html>
    <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>Your Course Match Insights</title>
        <script src="https://cdn.plot.ly/plotly-2.26.1.min.js"></script>
        <style>
            :root {
                --blue-dark: #1d4ed8;
                --blue: #2563eb;
                --blue-mid: #3b82f6;
                --blue-light: #60a5fa;
                --blue-pale: #93c5fd;
                --blue-bg: #eaf2ff;
                --ink: #0f2540;
                --muted: #5b6b82;
                --border: #d7e3f7;
                --bg: #ffffff;
            }
            * { box-sizing: border-box; }
            body {
                font-family: "DM Sans", "Avenir Next", "Segoe UI", sans-serif;
                margin: 0;
                padding: 20px;
                background: var(--bg);
                color: var(--ink);
            }
            h1 {
                font-family: Montserrat, "Avenir Next", "Segoe UI", sans-serif;
                font-size: 22px;
                margin: 0 0 4px 0;
                color: var(--blue-dark);
            }
            .subtitle {
                color: var(--muted);
                font-size: 14px;
                margin-bottom: 20px;
            }
            .chart-card {
                background: #fff;
                border: 1px solid var(--border);
                border-radius: 12px;
                padding: 16px 18px 8px 18px;
                margin-bottom: 20px;
                box-shadow: 0 3px 10px rgba(15, 37, 64, 0.08);
            }
            .chart-card h3 {
                font-family: Montserrat, "Avenir Next", "Segoe UI", sans-serif;
                font-size: 16px;
                margin: 0 0 2px 0;
                color: var(--ink);
            }
            .chart-card .caption {
                font-size: 13px;
                color: var(--muted);
                margin: 0 0 10px 0;
                max-width: 700px;
            }
            .empty-state {
                color: var(--muted);
                font-size: 14px;
                padding: 24px;
                text-align: center;
            }
            #loading {
                color: var(--muted);
                font-size: 14px;
                padding: 20px 0;
            }
        </style>
    </head>
    <body>
        <div id="loading">Loading your results…</div>
        <div id="content" style="display:none">
            <div class="chart-card">
                <h3>Which career pathways do these courses cover?</h3>
                <p class="caption">Each slice is a career pathway. Bigger slices mean more of the recommended courses fall into that area — useful for spotting where the bulk of your matches are.</p>
                <div id="pie" style="width:100%;max-width:820px;height:420px"></div>
            </div>

            <div class="chart-card">
                <h3>How closely do these courses match your current skills?</h3>
                <p class="caption">Bars further to the right mean a closer match to what's already on your resume. Bars further to the left mean the course would teach you more new material.</p>
                <div id="hist" style="width:100%;max-width:820px;height:360px"></div>
            </div>

            <div class="chart-card">
                <h3>Relevance vs. skill match, course by course</h3>
                <p class="caption">Each dot is one recommended course. Dots toward the top-right are both highly relevant to your resume and closely aligned with skills you already have — usually your safest, fastest wins. Dots toward the bottom-left are more of a stretch. Hover a dot to see the course.</p>
                <div id="scatter" style="width:100%;max-width:900px;height:440px"></div>
            </div>

            <div class="chart-card">
                <h3>Your most relevant courses</h3>
                <p class="caption">The same courses shown in your Recommendations list, ranked by their overall match score. Longer bars = stronger match.</p>
                <div id="bar" style="width:100%;max-width:900px;height:440px"></div>
            </div>

            <div id="history-section" style="display:none">
                <div class="chart-card">
                    <h3>Your past activity on these courses</h3>
                    <p class="caption">How many of the recommended courses you've already viewed, started, or completed before.</p>
                    <div id="history_bar" style="width:100%;max-width:900px;height:340px"></div>
                </div>

                <div class="chart-card">
                    <h3>Progress on courses you've completed</h3>
                    <p class="caption">How far you got in each course you finished, shown as a percentage.</p>
                    <div id="completed_progress" style="width:100%;max-width:900px;height:340px"></div>
                </div>
            </div>
        </div>

        <script>
            async function loadAndRender(){
                const loadingEl = document.getElementById('loading');
                try{
                    const r = await fetch('/feature_matrix');
                    const j = await r.json();

                    if(!j.rows || j.rows.length === 0){
                        loadingEl.outerHTML = '<div class="empty-state">No results yet. Submit a resume first, then reload this page to see your charts.</div>';
                        return;
                    }
                    const rows = j.rows;
                    loadingEl.style.display = 'none';
                    document.getElementById('content').style.display = 'block';

                    const pathwayCounts = {};
                    rows.forEach(r => { const k = r.primary_pathway || 'Unknown'; pathwayCounts[k] = (pathwayCounts[k]||0)+1; });

                    // ---- Pathway pie ----
                    const labels = Object.keys(pathwayCounts);
                    const values = labels.map(l=>pathwayCounts[l]);
                    Plotly.newPlot('pie', [{
                        type:'pie', labels:labels, values:values, hole:0.45,
                        textinfo:'label+percent', hovertemplate:'%{label}: %{value} course(s)<extra></extra>',
                        marker:{colors:['#1d4ed8','#2563eb','#3b82f6','#60a5fa','#93c5fd','#0ea5e9','#0369a1','#38bdf8']}
                    }], {
                        margin:{t:10,b:10,l:10,r:10}, showlegend:true,
                        legend:{orientation:'h', y:-0.15}
                    }, {displayModeBar:false, responsive:true});

                    // ---- Skill match histogram (gap_score inverted to "skill match") ----
                    const matchVals = rows.map(r => {
                        const gap = parseFloat(r.gap_score);
                        return isNaN(gap) ? null : (1 - gap);
                    }).filter(v => v !== null);
                    Plotly.newPlot('hist', [{
                        x: matchVals, type:'histogram', marker:{color: '#2563eb'},
                        hovertemplate:'Skill match: %{x:.0%}<br>Courses: %{y}<extra></extra>',
                        xbins:{start:0, end:1, size:0.1}
                    }], {
                        margin:{t:10,b:40,l:50,r:20},
                        xaxis:{title:'Skill match (higher = closer to what you already know)', tickformat:'.0%', range:[0,1]},
                        yaxis:{title:'Number of courses'}
                    }, {displayModeBar:false, responsive:true});

                    // ---- Scatter: relevance vs skill match, colored by pathway ----
                    const paired = rows.map(r=>({
                        x:parseFloat(r.skill_overlap),
                        y:parseFloat(r.tfidf_score),
                        p:r.primary_pathway||'Unknown',
                        title:r.title||r.course_code||'Course',
                        code:r.course_code||''
                    })).filter(o=>!isNaN(o.x)&&!isNaN(o.y));

                    const pathwaysList = [...new Set(paired.map(p=>p.p))];
                    const palette = ['#1d4ed8','#2563eb','#3b82f6','#60a5fa','#93c5fd','#0ea5e9','#0369a1','#38bdf8'];
                    const scatterTraces = pathwaysList.map((pw, i) => {
                        const pts = paired.filter(p => p.p === pw);
                        return {
                            x: pts.map(p=>p.x), y: pts.map(p=>p.y), mode:'markers', type:'scatter',
                            name: pw,
                            text: pts.map(p => p.code + ' — ' + p.title),
                            hovertemplate: '%{text}<br>Skill match: %{x:.0%}<br>Relevance: %{y:.2f}<extra></extra>',
                            marker:{size:10, opacity:0.75, color: palette[i % palette.length]}
                        };
                    });
                    Plotly.newPlot('scatter', scatterTraces, {
                        margin:{t:10,b:45,l:55,r:20},
                        xaxis:{title:'Skill match', tickformat:'.0%'},
                        yaxis:{title:'Relevance to your resume'},
                        legend:{orientation:'h', y:-0.2}
                    }, {displayModeBar:false, responsive:true});

                    // ---- Top courses (mirrors the Recommendations panel) ----
                    // Prefer rows the backend already flagged as recommended,
                    // ranked by the same weighted recommendation_score used
                    // in the Recommendations list — so this chart never
                    // disagrees with what's actually shown there. Older
                    // cached exports (before this field existed) fall back
                    // to an approximate ranking by tfidf_score.
                    const hasRecommendedFlag = rows.some(r => 'is_recommended' in r);
                    let top;
                    if (hasRecommendedFlag) {
                        const recommendedRows = rows.filter(r => r.is_recommended === true || r.is_recommended === 'True');
                        const seen = new Set();
                        top = recommendedRows
                            .map(r => ({
                                code: r.course_code || '',
                                label: r.title ? (r.course_code ? r.course_code + ' — ' + r.title : r.title) : (r.course_code || 'Unknown'),
                                score: parseFloat(r.recommendation_score)
                            }))
                            .filter(t => !isNaN(t.score) && !seen.has(t.code) && seen.add(t.code))
                            .sort((a,b) => b.score - a.score)
                            .slice(0,12)
                            .reverse();
                    } else {
                        const byCourse = {};
                        rows.forEach(r=>{
                            const k = (r.course_code || r.title || 'Unknown');
                            const label = r.title ? (r.course_code ? r.course_code + ' — ' + r.title : r.title) : k;
                            const v = parseFloat(r.tfidf_score);
                            if(!isNaN(v)){ if(!byCourse[k]) byCourse[k] = {vals:[], label:label}; byCourse[k].vals.push(v); }
                        });
                        const avg = Object.values(byCourse).map(o => ({ label:o.label, score: o.vals.reduce((a,b)=>a+b,0)/o.vals.length }));
                        avg.sort((a,b)=>b.score-a.score);
                        top = avg.slice(0,12).reverse();
                    }
                    Plotly.newPlot('bar', [{
                        x:top.map(t=>t.score), y:top.map(t=>t.label), type:'bar', orientation:'h',
                        marker:{color:'#2563eb'},
                        hovertemplate:'%{y}<br>Overall match score: %{x:.2f}<extra></extra>'
                    }], {
                        margin:{t:10,b:40,l:260,r:20},
                        xaxis:{title: hasRecommendedFlag ? 'Overall match score' : 'Relevance to your resume (approximate)'}
                    }, {displayModeBar:false, responsive:true});

                    // ---- Learning history (optional) ----
                    const validHistory = rows.filter(r => ['completed','started','viewed'].includes((r.history_action||'').toLowerCase()));
                    if (validHistory.length) {
                        document.getElementById('history-section').style.display = 'block';

                        const actionLabels = { completed: 'Completed', started: 'In progress', viewed: 'Viewed only' };
                        const counts = validHistory.reduce((acc, r) => {
                            const action = (r.history_action||'').toLowerCase();
                            acc[action] = (acc[action]||0) + 1;
                            return acc;
                        }, {});
                        const order = ['completed','started','viewed'].filter(k => counts[k]);
                        Plotly.newPlot('history_bar', [{
                            x: order.map(k => actionLabels[k] || k),
                            y: order.map(k => counts[k]),
                            type:'bar',
                            marker:{color: order.map(k => k==='completed' ? '#1d4ed8' : k==='started' ? '#3b82f6' : '#93c5fd')},
                            hovertemplate:'%{x}: %{y} course(s)<extra></extra>'
                        }], {
                            margin:{t:10,b:40,l:50,r:20},
                            yaxis:{title:'Number of courses'}
                        }, {displayModeBar:false, responsive:true});

                        const completed = validHistory.filter(r => (r.history_action||'').toLowerCase()==='completed');
                        if (completed.length) {
                            const sorted = completed.slice().sort((a,b) => (parseFloat(b.history_progress)||0) - (parseFloat(a.history_progress)||0)).slice(0,12);
                            const courseLabels = sorted.map(r => r.course_code || r.title || 'Unknown');
                            const courseProgress = sorted.map(r => parseFloat(r.history_progress) || 0);
                            Plotly.newPlot('completed_progress', [{
                                x:courseLabels, y:courseProgress, type:'bar', marker:{color:'#2563eb'},
                                hovertemplate:'%{x}<br>Progress: %{y:.0%}<extra></extra>'
                            }], {
                                margin:{t:10,b:80,l:50,r:20},
                                xaxis:{title:''}, yaxis:{title:'Progress', tickformat:'.0%'}
                            }, {displayModeBar:false, responsive:true});
                        }
                    }
                }catch(e){
                    loadingEl.outerHTML = '<div class="empty-state">Something went wrong loading your charts: ' + e.toString() + '</div>';
                }
            }
            loadAndRender();
        </script>
    </body>
</html>
"""
    return HTMLResponse(content=html, status_code=200)


@app.get("/health")
async def health():
    return {"status": "ok"}