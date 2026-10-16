/* 01_load_and_explore.sas */
/* Import feature_matrix.csv and examine column distributions. */

libname mycas cas;

proc import datafile="/path/to/feature_matrix.csv"
    out=work.feature_matrix
    dbms=csv
    replace;
    getnames=yes;
run;

proc contents data=work.feature_matrix; run;
proc means data=work.feature_matrix n mean std min max;
    var skill_overlap gap_score prereq_match audience_match pathway_match tfidf_score;
run;

proc freq data=work.feature_matrix;
    tables primary_pathway / nocum nopercent;
run;

