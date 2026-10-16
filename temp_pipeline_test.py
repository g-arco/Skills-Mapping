import time
from pathlib import Path
from python_pipeline.course_data import load_courses, prepare_course_dataframe
from python_pipeline.parser import normalize_text
from python_pipeline.skills import extract_skills
from python_pipeline.feature_matrix import build_feature_matrix

text = normalize_text("This is a test resume with Python, SQL, and analytics experience.")
print('resume length', len(text))

start = time.time()
path = Path('data/EDU_PRODUCTS.csv')
df = load_courses(path)
print('load_courses', time.time() - start, 'seconds', 'rows', len(df))

start = time.time()
df2 = prepare_course_dataframe(df)
print('prepare_course_dataframe', time.time() - start, 'seconds')

start = time.time()
skills = extract_skills(text)
print('extract_skills', time.time() - start, 'seconds', 'skills', skills[:10])

start = time.time()
feature_df = build_feature_matrix(
    resume_text=text,
    extracted_skills=skills,
    courses_df=df2,
    user_level='beginner',
    target_pathways=['Analytics'],
    resume_audience_terms=['analytics'],
)
print('build_feature_matrix', time.time() - start, 'seconds')
print(feature_df.head().to_dict('records')[:2])
