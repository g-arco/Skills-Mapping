/* 03_export_scores.sas */
/* Score feature_matrix.csv using trained SAS model and export results. */

libname mycas cas;

proc casutil;
    load casdata="course_recommendation_model" incaslib="casuser" outcaslib="casuser"; /* model already saved */
quit;

proc astore.load inmodel="casuser.course_recommendation_model" out=work.model; run;

proc astore.score data=casuser.feature_matrix out=work.scores copyvars=(course_code title primary_pathway);
    id course_code;
    score result=score;
run;

proc export data=work.scores outfile="/path/to/sas_scores.csv" dbms=csv replace;
run;
