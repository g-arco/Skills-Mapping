/* 02_train_model.sas */
/* Train a simple recommendation model on the feature matrix. */

libname mycas cas;

proc casutil;
    load datafile="/path/to/feature_matrix.csv" outcaslib="casuser" casout="feature_matrix" replace;
quit;

proc forest data=casuser.feature_matrix seed=12345;
    target skill_overlap;
    input gap_score prereq_match audience_match pathway_match tfidf_score / level=interval;
    save casdata="course_recommendation_model" caslib="casuser" replace;
run;
