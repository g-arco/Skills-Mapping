/* 04_prepare_va_data.sas */
/* Prepare scored course recommendations for SAS Visual Analytics. */

libname mycas cas;

proc import datafile="/path/to/sas_scores.csv"
    out=work.sas_scores
    dbms=csv
    replace;
    getnames=yes;
run;

data work.va_dashboard;
    set work.sas_scores;
    length recommendation_category $32.;
    if score >= 0.75 then recommendation_category = 'Strong';
    else if score >= 0.5 then recommendation_category = 'Recommended';
    else recommendation_category = 'Consider';
run;

proc casutil;
    save casdata="va_dashboard" incaslib="work" outcaslib="casuser" casout="VA_DASHBOARD" replace;
quit;
