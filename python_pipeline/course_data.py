import re
import pandas as pd
from pathlib import Path
from typing import List

REQUIRED_COLUMNS = [
    "PRODUCTCODE",
    "COURSE_TITLE_GLOBAL",
    "short_desc",
    "CURRICULUM",
    "PRIMARY_LEARNING_PATHWAY",
    "LEVEL",
    "SKILLS_LEARNED",
    "PREREQUISITES",
    "AUDIENCE",
    "language",
    "CONTENTFAMILYCODE",
    "COUNTRYCODE",
    "COUNTRYTITLE",
    "delivery_format",
    "delivery_format_title",
    "product_type",
    "IS_AVAILABLE_IN_IRIS",
    "ISACTIVE",
]

def load_courses(
    csv_path: Path | str | None = None,
    sas_config: str | None = None,
    cas_host: str | None = None,
    cas_port: int | None = None,
    cas_protocol: str = "http",
    cas_user: str | None = None,
    cas_password: str | None = None,
    cas_authinfo: str | None = None,
) -> pd.DataFrame:
    # If no path provided, try to discover a CSV under the repository `data/` folder.
    if csv_path is None:
        repo_root = Path(__file__).resolve().parents[1]
        data_dir = repo_root / "data"
        candidate = data_dir / "EDU_PRODUCTS.csv"
        if candidate.is_file():
            csv_path = candidate
        else:
            # if there's exactly one csv in data/, use it
            if data_dir.is_dir():
                csv_files = list(data_dir.glob("*.csv"))
                if len(csv_files) == 1:
                    csv_path = csv_files[0]
                elif len(csv_files) == 0:
                    raise ValueError(
                        f"No CSV files found in data/ and no csv_path provided."
                    )
                else:
                    raise ValueError(
                        f"Multiple CSV files found in data/; pass `csv_path` explicitly."
                    )
            else:
                raise ValueError(
                    "No csv_path provided and data/ directory not found in repository root."
                )

    csv_path_str = str(csv_path)
    path = Path(csv_path_str)
    if path.is_file():
        df = pd.read_csv(path, low_memory=False)
    else:
        raise ValueError(
            "Course catalog CSV not found. Place the CSV in the repository `data/` folder or pass an explicit `csv_path`."
        )

    # Canonicalize columns to the lowercase names expected downstream.
    # Map common source headers (case-insensitive) to canonical names used across the codebase.
    canonical_map = {
        "productcode": "course_code",
        "course_code": "course_code",
        "course_title_global": "title",
        "title": "title",
        "short_desc": "short_desc",
        "short_description": "short_desc",
        "curriculum": "curriculum",
        "primary_learning_pathway": "primary_learning_pathway",
        "primary_learning_path": "primary_learning_pathway",
        "primary_pathway": "primary_learning_pathway",
        "level": "level",
        "course_level": "level",
        "skills_learned": "skills_learned",
        "skills": "skills_learned",
        "skill": "skills_learned",
        "prerequisites": "prerequisites",
        "prereq": "prerequisites",
        "audience": "audience",
        "isactive": "is_active",
    }

    rename_map = {}
    for col in df.columns:
        key = col.lower()
        if key in canonical_map:
            rename_map[col] = canonical_map[key]
    if rename_map:
        df = df.rename(columns=rename_map)

    # Ensure all required canonical columns exist (fill defaults when possible)
    required_canonical = [
        "course_code",
        "title",
        "short_desc",
        "curriculum",
        "primary_learning_pathway",
        "level",
        "skills_learned",
        "prerequisites",
        "audience",
    ]

    missing = [c for c in required_canonical if c not in df.columns]
    for col in missing:
        if col == "audience":
            df[col] = "all"
        elif col == "primary_learning_pathway":
            df[col] = "General"
        else:
            df[col] = ""

    missing = [c for c in required_canonical if c not in df.columns]
    if missing:
        raise ValueError(f"Course catalog source is missing required columns: {missing}")

    return df.copy()


def _load_courses_from_sas(
    source: str,
    sas_config: str | None = None,
    cas_host: str | None = None,
    cas_port: int | None = None,
    cas_protocol: str = "http",
    cas_user: str | None = None,
    cas_password: str | None = None,
    cas_authinfo: str | None = None,
) -> pd.DataFrame:
    raise RuntimeError(
        "SAS/CAS loading is not supported in this environment. Provide a local CSV in the `data/` folder or pass `csv_path`."
    )


def _load_courses_from_cas(
    source: str,
    cas_host: str | None = None,
    cas_port: int | None = None,
    cas_protocol: str = "http",
    cas_user: str | None = None,
    cas_password: str | None = None,
    cas_authinfo: str | None = None,
) -> pd.DataFrame:
    raise RuntimeError(
        "CAS loading is not supported. Provide a local CSV in the `data/` folder or pass `csv_path`."
    )


def prepare_course_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    courses = df.copy()
    # Ensure expected canonical columns exist and normalize/clean values
    canonical_cols = [
        "course_code",
        "title",
        "short_desc",
        "curriculum",
        "primary_learning_pathway",
        "level",
        "skills_learned",
        "prerequisites",
        "audience",
    ]
    for col in canonical_cols:
        if col not in courses.columns:
            courses[col] = (
                "all"
                if col == "audience"
                else ("General" if col == "primary_learning_pathway" else ("all" if col == "level" else ""))
            )

    courses["short_desc"] = courses["short_desc"].fillna("")
    courses["curriculum"] = courses["curriculum"].fillna("")
    courses["skills_learned"] = courses["skills_learned"].fillna("")
    courses["prerequisites"] = courses["prerequisites"].fillna("")
    courses["audience"] = courses["audience"].fillna("all")
    courses["primary_learning_pathway"] = courses["primary_learning_pathway"].fillna("General")
    courses["level"] = courses["level"].fillna("all")
    if "is_active" not in courses.columns:
        courses["is_active"] = "Y"
    courses["is_active"] = courses["is_active"].fillna("").astype(str).str.strip().str.upper()

    def _split_skills(value: str) -> list:
        if not value:
            return []
        parts = [p.strip() for p in re.split(r"[;,/|]+", str(value)) if p.strip()]
        return parts

    courses["skills_list"] = courses["skills_learned"].astype(str).apply(_split_skills)

    courses["combined_text"] = (
        courses["title"].astype(str)
        + " "
        + courses["short_desc"].astype(str)
        + " "
        + courses["curriculum"].astype(str)
        + " "
        + courses["skills_learned"].astype(str)
        + " "
        + courses["level"].astype(str)
    )

    courses = courses.rename(columns={"primary_learning_pathway": "primary_pathway"})
    return courses


def export_unique_courses_considered(
    df: pd.DataFrame,
    language: str = "en",
    output_path: str | Path | None = None,
) -> pd.DataFrame:
    """Return and optionally export the unique, active, language-matched course catalog."""
    courses = df.copy()

    if "course_code" not in courses.columns and "PRODUCTCODE" in courses.columns:
        courses = courses.rename(columns={"PRODUCTCODE": "course_code"})

    if "is_active" not in courses.columns:
        courses["is_active"] = "Y"
    courses["is_active"] = courses["is_active"].fillna("").astype(str).str.strip().str.upper()

    if "language" not in courses.columns:
        courses["language"] = language

    requested = language.lower()
    courses["language"] = courses["language"].fillna("").astype(str).str.strip().str.lower()
    eligible = courses[
        courses["is_active"].eq("Y")
        & courses["language"].isin([requested, "english", "en", "en-us", "eng"])
    ].copy()
    eligible = eligible.drop_duplicates(subset=["course_code"], keep="first").reset_index(drop=True)

    output = pd.DataFrame({
        "PRODUCTCODE": eligible["course_code"].astype(str),
        "COURSE_TITLE_GLOBAL": eligible["title"].astype(str) if "title" in eligible.columns else "",
        "short_desc": eligible["short_desc"].astype(str) if "short_desc" in eligible.columns else "",
        "CURRICULUM": eligible["curriculum"].astype(str) if "curriculum" in eligible.columns else "",
        "PRIMARY_LEARNING_PATHWAY": eligible["primary_pathway"].astype(str) if "primary_pathway" in eligible.columns else (eligible["primary_learning_pathway"].astype(str) if "primary_learning_pathway" in eligible.columns else ""),
        "LEVEL": eligible["level"].astype(str) if "level" in eligible.columns else "",
        "SKILLS_LEARNED": eligible["skills_learned"].astype(str) if "skills_learned" in eligible.columns else "",
        "PREREQUISITES": eligible["prerequisites"].astype(str) if "prerequisites" in eligible.columns else "",
        "AUDIENCE": eligible["audience"].astype(str) if "audience" in eligible.columns else "",
        "language": eligible["language"].astype(str) if "language" in eligible.columns else "",
        "CONTENTFAMILYCODE": eligible["contentfamilycode"].astype(str) if "contentfamilycode" in eligible.columns else (eligible["CONTENTFAMILYCODE"].astype(str) if "CONTENTFAMILYCODE" in eligible.columns else ""),
        "COUNTRYCODE": eligible["countrycode"].astype(str) if "countrycode" in eligible.columns else (eligible["COUNTRYCODE"].astype(str) if "COUNTRYCODE" in eligible.columns else ""),
        "COUNTRYTITLE": eligible["countrytitle"].astype(str) if "countrytitle" in eligible.columns else (eligible["COUNTRYTITLE"].astype(str) if "COUNTRYTITLE" in eligible.columns else ""),
        "delivery_format": eligible["delivery_format"].astype(str) if "delivery_format" in eligible.columns else "",
        "delivery_format_title": eligible["delivery_format_title"].astype(str) if "delivery_format_title" in eligible.columns else "",
        "product_type": eligible["product_type"].astype(str) if "product_type" in eligible.columns else "",
        "IS_AVAILABLE_IN_IRIS": eligible["is_available_in_iris"].astype(str) if "is_available_in_iris" in eligible.columns else (eligible["IS_AVAILABLE_IN_IRIS"].astype(str) if "IS_AVAILABLE_IN_IRIS" in eligible.columns else ""),
        "ISACTIVE": eligible["is_active"].astype(str) if "is_active" in eligible.columns else (eligible["ISACTIVE"].astype(str) if "ISACTIVE" in eligible.columns else ""),
    })

    output = output[REQUIRED_COLUMNS]
    if output_path is not None:
        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        output.to_csv(out_path, index=False)
    return output
