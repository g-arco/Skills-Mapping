import unittest
from io import StringIO

import pandas as pd

from python_pipeline.feature_matrix import (
    _prerequisite_match,
    attach_course_history,
    parse_course_history,
)
from python_pipeline.recommender import recommend_from_engagement
from python_pipeline.course_data import prepare_course_dataframe, export_unique_courses_considered


class FeatureMatrixHistoryTests(unittest.TestCase):
    def test_prerequisite_match_handles_prose_and_html_lists(self) -> None:
        vocabulary = {
            "sas viya", "unix", "unix commands", "sas enterprise miner",
            "pattern discovery", "predictive modeling", "statistics", "regression modeling",
            "basic statistics", "microsoft windows",
        }

        self.assertAlmostEqual(
            _prerequisite_match(
                "Before attending this course, you should be familiar with the SAS Viya environment, Unix environments, and Unix commands.",
                {"sas viya"},
                vocabulary,
            ),
            0.5,
        )
        self.assertAlmostEqual(
            _prerequisite_match(
                "Before attending, you should have at least an introductory-level familiarity with basic statistics and regression modeling.<br><br><ul><li>be acquainted with Microsoft Windows</li></ul>",
                {"statistics", "regression"},
                vocabulary,
            ),
            0.6667,
        )

    def test_prerequisite_match_treats_no_prerequisites_as_full_match(self) -> None:
        self.assertEqual(
            _prerequisite_match("There are no formal prerequisites for this course.", set(), {"sas"}),
            1.0,
        )

    def test_parse_course_history_normalizes_user_email_and_progress(self) -> None:
        csv_data = StringIO(
            "course_code,elearning_platform,email,status,progress_course\n"
            "C001,current,gabrielle_mae_arco@dlsu.edu.ph,completed,85%\n"
            "C002,current,GABRIELLE_MAE_ARCO@DLSU.EDU.PH,started,0.35\n"
            "C003,legacy,gabrielle_mae_arco@dlsu.edu.ph,completed,100%\n"
        )

        history_df = parse_course_history(csv_data)

        self.assertEqual(len(history_df), 2)
        self.assertListEqual(history_df["course_code"].tolist(), ["C001", "C002"])
        self.assertEqual(history_df.loc[history_df["course_code"] == "C001", "email"].iloc[0], "gabrielle_mae_arco@dlsu.edu.ph")
        self.assertEqual(history_df.loc[history_df["course_code"] == "C002", "history_action"].iloc[0], "started")
        self.assertAlmostEqual(history_df.loc[history_df["course_code"] == "C001", "history_progress"].iloc[0], 0.85)
        self.assertAlmostEqual(history_df.loc[history_df["course_code"] == "C002", "history_progress"].iloc[0], 0.35)

    def test_attach_course_history_matches_courses_to_history_rows(self) -> None:
        courses_df = pd.DataFrame(
            [
                {"course_code": "C001", "title": "Course One"},
                {"course_code": "C002", "title": "Course Two"},
            ]
        )
        history_df = pd.DataFrame(
            [
                {
                    "course_code": "C001",
                    "email": "gabrielle_mae_arco@dlsu.edu.ph",
                    "elearning_platform": "current",
                    "history_action": "completed",
                    "history_progress": 0.85,
                }
            ]
        )

        attached = attach_course_history(courses_df, history_df)

        self.assertEqual(attached.loc[attached["course_code"] == "C001", "history_action"].iloc[0], "completed")
        self.assertAlmostEqual(attached.loc[attached["course_code"] == "C001", "history_progress"].iloc[0], 0.85)
        self.assertEqual(attached.loc[attached["course_code"] == "C002", "history_action"].iloc[0], "")
        self.assertAlmostEqual(attached.loc[attached["course_code"] == "C002", "history_progress"].iloc[0], 0.0)

    def test_parse_course_history_prefers_highest_progress_for_duplicate_course_codes(self) -> None:
        csv_data = StringIO(
            "course_code,elearning_platform,email,status,progress_course\n"
            "C001,current,gabrielle_mae_arco@dlsu.edu.ph,started,40%\n"
            "C001,current,gabrielle_mae_arco@dlsu.edu.ph,completed,85%\n"
            "C002,current,gabrielle_mae_arco@dlsu.edu.ph,viewed,20%\n"
        )

        history_df = parse_course_history(csv_data)

        self.assertEqual(len(history_df), 2)
        self.assertEqual(history_df.loc[history_df["course_code"] == "C001", "history_action"].iloc[0], "completed")
        self.assertAlmostEqual(history_df.loc[history_df["course_code"] == "C001", "history_progress"].iloc[0], 0.85)
        self.assertEqual(history_df.loc[history_df["course_code"] == "C002", "history_action"].iloc[0], "viewed")
        self.assertAlmostEqual(history_df.loc[history_df["course_code"] == "C002", "history_progress"].iloc[0], 0.2)

    def test_engagement_recommendations_are_email_scoped_and_skip_completed_courses(self) -> None:
        history_df = parse_course_history(StringIO(
            "course_code,elearning_platform,email,status,progress_course\n"
            "C001,current,learner@example.com,completed,100%\n"
            "C002,current,other@example.com,completed,100%\n"
            "C003,current,learner@example.com,viewed,20%\n"
        ), email="learner@example.com")
        courses_df = pd.DataFrame([
            {"course_code": "C001", "title": "Python Basics", "skills_list": ["python"], "primary_pathway": "Data"},
            {"course_code": "C002", "title": "Other Course", "skills_list": ["sql"], "primary_pathway": "Data"},
            {"course_code": "C003", "title": "Python Follow-up", "skills_list": ["python"], "primary_pathway": "Data"},
            {"course_code": "C004", "title": "SQL Next", "skills_list": ["sql"], "primary_pathway": "Data"},
        ])

        ranked, profile = recommend_from_engagement(courses_df, history_df)

        self.assertEqual(profile["completed_courses"], 1)
        self.assertIn("C004", ranked["course_code"].tolist())
        self.assertNotIn("C002", profile["learned_skills"])
        self.assertNotIn("C001", ranked["course_code"].tolist())

    def test_parse_course_history_coalesces_email_alias_columns(self) -> None:
        history_df = parse_course_history(StringIO(
            "ecode,elearning_platform,email,sasemail,status,progress_course\n"
            "C001,current,,gabrielle_mae_arco@dlsu.edu.ph,completed,100%\n"
        ), email="gabrielle_mae_arco@dlsu.edu.ph")

        self.assertEqual(len(history_df), 1)
        self.assertEqual(history_df.iloc[0]["email"], "gabrielle_mae_arco@dlsu.edu.ph")

    def test_email_filter_keeps_all_courses_for_one_learner(self) -> None:
        history_df = parse_course_history(StringIO(
            "ecode,elearning_platform,email,status,progress_course\n"
            "C001,current,gabrielle_mae_arco@dlsu.edu.ph,completed,100%\n"
            "C002,current,gabrielle_mae_arco@dlsu.edu.ph,started,60%\n"
            "C003,current,another@example.com,completed,100%\n"
        ), email="gabrielle_mae_arco@dlsu.edu.ph")

        self.assertEqual(history_df["course_code"].tolist(), ["C001", "C002"])
        self.assertTrue((history_df["email"] == "gabrielle_mae_arco@dlsu.edu.ph").all())

    def test_course_catalog_keeps_only_unique_active_requested_language_courses(self) -> None:
        catalog = pd.DataFrame([
            {"course_code": "C001", "title": "Active English", "is_active": "Y", "language": "English"},
            {"course_code": "C001", "title": "Duplicate English", "is_active": "Y", "language": "en"},
            {"course_code": "C002", "title": "Inactive English", "is_active": "N", "language": "en"},
            {"course_code": "C003", "title": "Active Spanish", "is_active": "Y", "language": "es"},
        ])
        prepared = prepare_course_dataframe(catalog)

        eligible = prepared[
            prepared["is_active"].eq("Y")
            & prepared["language"].str.lower().isin(["english", "en"])
        ].drop_duplicates("course_code")

        self.assertEqual(eligible["course_code"].tolist(), ["C001"])

    def test_engagement_status_weight_changes_skill_score(self) -> None:
        courses_df = pd.DataFrame([
            {"course_code": "C001", "title": "Source", "skills_list": ["python"], "primary_pathway": "Data"},
            {"course_code": "C002", "title": "Next", "skills_list": ["python"], "primary_pathway": "Data"},
        ])
        completed_history = pd.DataFrame([
            {"course_code": "C001", "history_action": "completed", "history_progress": 1.0},
        ])
        viewed_history = pd.DataFrame([
            {"course_code": "C001", "history_action": "viewed", "history_progress": 1.0},
        ])

        completed_ranked, _ = recommend_from_engagement(courses_df, completed_history)
        viewed_ranked, _ = recommend_from_engagement(courses_df, viewed_history)

        completed_score = completed_ranked.loc[completed_ranked["course_code"] == "C002", "recommendation_score"].iloc[0]
        viewed_score = viewed_ranked.loc[viewed_ranked["course_code"] == "C002", "recommendation_score"].iloc[0]
        self.assertGreater(completed_score, viewed_score)

    def test_engagement_profile_verifies_named_prerequisite_course_completion(self) -> None:
        courses_df = pd.DataFrame([
            {
                "course_code": "C001",
                "title": "Statistics You Need to Know for Machine Learning",
                "skills_list": ["statistics"],
                "primary_pathway": "Data",
                "prerequisites": "None",
            },
            {
                "course_code": "C002",
                "title": "Machine Learning Using SAS Viya",
                "skills_list": ["machine learning"],
                "primary_pathway": "Data",
                "prerequisites": "<ul><li>Statistics You Need to Know for Machine Learning</li><li>Machine Learning Using SAS Viya</li></ul>",
            },
            {
                "course_code": "C003",
                "title": "Advanced Modeling",
                "skills_list": ["modeling"],
                "primary_pathway": "Data",
                "prerequisites": "Before attending, complete the Statistics You Need to Know for Machine Learning course.",
            },
        ])
        history_df = pd.DataFrame([
            {"course_code": "C001", "history_action": "completed", "history_progress": 1.0},
        ])

        ranked, profile = recommend_from_engagement(courses_df, history_df)

        c002 = ranked.loc[ranked["course_code"] == "C002"].iloc[0]
        self.assertEqual(c002["prerequisite_courses"][0]["title"], "Statistics You Need to Know for Machine Learning")
        self.assertTrue(c002["prerequisite_courses"][0]["completed"])
        self.assertEqual(c002["prerequisite_courses"][1]["completed"], False)
        self.assertAlmostEqual(c002["prereq_match"], 0.5)
        self.assertTrue(any(check["course_code"] == "C002" for check in profile["prerequisite_checks"]))

    def test_export_unique_courses_considered_filters_active_english_unique_courses(self) -> None:
        catalog = pd.DataFrame([
            {"course_code": "C001", "title": "English Active", "short_desc": "A", "curriculum": "X", "primary_pathway": "Data", "level": "Beginner", "skills_learned": "Python", "prerequisites": "None", "audience": "All", "is_active": "Y", "language": "English"},
            {"course_code": "C001", "title": "Duplicate English", "short_desc": "B", "curriculum": "X", "primary_pathway": "Data", "level": "Beginner", "skills_learned": "Python", "prerequisites": "None", "audience": "All", "is_active": "Y", "language": "en"},
            {"course_code": "C002", "title": "Inactive English", "short_desc": "C", "curriculum": "X", "primary_pathway": "Data", "level": "Beginner", "skills_learned": "Python", "prerequisites": "None", "audience": "All", "is_active": "N", "language": "en"},
            {"course_code": "C003", "title": "Spanish Active", "short_desc": "D", "curriculum": "X", "primary_pathway": "Data", "level": "Beginner", "skills_learned": "Python", "prerequisites": "None", "audience": "All", "is_active": "Y", "language": "es"},
        ])

        export_path = "test_unique_courses_considered.csv"
        result = export_unique_courses_considered(catalog, output_path=export_path)

        self.assertEqual(result["PRODUCTCODE"].tolist(), ["C001"])
        self.assertEqual(result.columns.tolist(), [
            "PRODUCTCODE",
            "COURSE_TITLE_GLOBAL",
            "short_desc",
            "CURRICULUM",
            "PRIMARY_LEARNING_PATHWAY",
            "LEVEL",
            "SKILLS_LEARNED",
            "PREREQUISITES",
            "AUDIENCE",
        ])

        try:
            import os
            os.remove(export_path)
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    unittest.main()
