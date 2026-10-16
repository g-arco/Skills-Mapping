import unittest

from python_pipeline.skills import extract_skills


class SkillExtractionTests(unittest.TestCase):
    def test_extracts_common_technology_skills_from_resume_text(self) -> None:
        resume_text = """
        Cynthia Dwayne
        Software Developer

        Skills
        JavaScript / React
        Java
        SQL
        REST API Integration
        Technical Troubleshooting
        Cross-functional Collaboration
        Problem Solving
        """

        skills = extract_skills(resume_text)

        self.assertIn("sql", skills)
        self.assertIn("problem solving", skills)
        self.assertIn("javascript", skills)
        self.assertIn("react", skills)
        self.assertIn("java", skills)
        self.assertIn("rest api integration", skills)
        self.assertIn("technical troubleshooting", skills)
        self.assertIn("cross-functional collaboration", skills)


if __name__ == "__main__":
    unittest.main()
