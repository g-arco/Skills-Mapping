import argparse
from pathlib import Path

from .parser import extract_audience_profile, read_resume_text
from .skills import extract_skills
from .course_data import load_courses, prepare_course_dataframe, export_unique_courses_considered
from .feature_matrix import (
    attach_course_history,
    build_and_export_features,
    build_feature_matrix,
    parse_course_history,
)
from .recommender import recommend_top_courses


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a skills mapping feature matrix from resume text and course catalog data.")
    parser.add_argument("--resume-text", required=True, help="Path to a resume text file or PDF")
    parser.add_argument("--courses-csv", required=True, help="Path to course catalog CSV, SAS libref.table, or CAS URI like cas://host:port/caslib.table")
    parser.add_argument("--sas-config", default=None, help="saspy config name to use for SAS library access on Windows")
    parser.add_argument("--cas-host", default=None, help="CAS server host for swat CAS access")
    parser.add_argument("--cas-port", type=int, default=None, help="CAS server port for swat CAS access")
    parser.add_argument("--cas-protocol", default="http", choices=["http", "https"], help="Protocol to use for swat CAS access")
    parser.add_argument("--cas-user", default=None, help="CAS username for swat CAS access")
    parser.add_argument("--cas-password", default=None, help="CAS password for swat CAS access")
    parser.add_argument("--cas-authinfo", default=None, help="CAS authinfo entry name for swat CAS access")
    parser.add_argument("--output-dir", default="data/handoff", help="Directory to write the feature matrix CSV")
    parser.add_argument("--user-level", default="beginner", choices=["beginner", "intermediate", "advanced"], help="Candidate experience level")
    parser.add_argument("--target-pathways", default="", help="Comma-separated preferred learning pathways")
    parser.add_argument("--top-n", type=int, default=10, help="Number of recommended courses to print")
    parser.add_argument("--no-embedding-cache", action="store_true", help="Disable the on-disk course embedding cache and always re-encode the catalog")
    parser.add_argument("--language", default="en", help="Preferred course language as an ISO 639-1 two-letter code (e.g. en, es, fr, de, zh)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    resume_text = read_resume_text(args.resume_text)
    course_df = load_courses(
        args.courses_csv,
        sas_config=args.sas_config,
        cas_host=args.cas_host,
        cas_port=args.cas_port,
        cas_protocol=args.cas_protocol,
        cas_user=args.cas_user,
        cas_password=args.cas_password,
        cas_authinfo=args.cas_authinfo,
    )
    course_df = prepare_course_dataframe(course_df)
    unique_courses_path = Path(args.output_dir) / "unique_courses_considered.csv"
    unique_course_df = export_unique_courses_considered(course_df, language=args.language, output_path=unique_courses_path)
    print(f"[Exporter] Unique courses considered written → {unique_courses_path}")
    print(f"[Exporter] {len(unique_course_df)} unique considered courses exported")
    extracted_skills = extract_skills(resume_text)
    audience_profile = extract_audience_profile(resume_text)
    print(f"[Pipeline] Extracted {len(extracted_skills)} resume skills: {extracted_skills[:12]}")
    print(f"[Pipeline] Detected job titles: {audience_profile['job_titles']}")
    print(f"[Pipeline] Detected education: {audience_profile['education']}")
    output_path = Path(args.output_dir) / "feature_matrix.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    history_path = Path("data") / "EDU_ENGAGEMENTS.csv"
    if history_path.exists():
        try:
            with history_path.open("rb") as fh:
                history_df = parse_course_history(fh)
            if not history_df.empty:
                course_df = attach_course_history(course_df, history_df)
                print(f"[Pipeline] Attached {len(history_df)} history rows from {history_path}")
        except Exception as exc:
            print(f"[Pipeline] Failed to load history: {exc}")

    target_pathways = [p.strip() for p in args.target_pathways.split(",") if p.strip()] or None

    # Compute the feature matrix ONCE (this is what loads the sentence-transformer
    # model and encodes the full course catalog) and reuse it for export instead
    # of recomputing it a second time.
    feature_df = build_feature_matrix(
        resume_text=resume_text,
        extracted_skills=extracted_skills,
        courses_df=course_df,
        user_level=args.user_level,
        target_pathways=target_pathways,
        resume_audience_terms=audience_profile["audience_terms"],
        use_disk_cache=not args.no_embedding_cache,
        user_language=args.language,
    )
    build_and_export_features(
        resume_text=resume_text,
        extracted_skills=extracted_skills,
        courses_df=course_df,
        user_level=args.user_level,
        target_pathways=target_pathways,
        resume_audience_terms=audience_profile["audience_terms"],
        output_path=output_path,
        feature_df=feature_df,
        user_language=args.language,
    )
    scored_df = recommend_top_courses(feature_df)
    print("\n[Pipeline] Top recommended courses")
    print(scored_df[["course_code", "title", "recommendation_score"]].head(args.top_n).to_string(index=False))


if __name__ == "__main__":
    main()