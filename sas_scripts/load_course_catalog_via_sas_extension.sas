/*
 Load the CAS course table using the SAS VS Code extension and PROC PYTHON.

 Use this file within the SAS Extension connected to cisviya.sas.com.

 This example uses SWAT in the SAS compute Python environment to read the CAS table
 and save it to a local CSV or work with it directly in Python.
*/

cas casmain
   host = /*change to correct server*/
   port =  /*change to correct port*/
   sessopts = (
      caslib = casuser
      timeout = 1800
      locale = "en_US"
   )
;

/* create a libname to your casuser caslib and Edu Gen */
libname casuser cas caslib = casuser sessref = casmain datalimit=all;;

/*change to correct caslib for your environment*/
libname eduprod cas caslib = "eduprod" sessref = casmain access = readonly datalimit=all;;
libname edugen cas caslib = "edugen" sessref = casmain access = readonly datalimit=all;;


/* Export the CAS table to CSV from inside SAS/Viya. */
data casuser.edu_products_out / sessref=casmain;
    set eduprod.table1 (datalimit=all);/* Export the CAS table to CSV from inside SAS/Viya. */
run;

/* Export the CAS table to CSV from inside SAS/Viya. */
data casuser.all_engagements_out / sessref=casmain;
    set edugen.table2(datalimit=all); /* Export the CAS table to CSV from inside SAS/Viya. */
run;
/* Export the CAS table to CSV from inside SAS/Viya. */
filename outcsv '/tmp/EDU_PRODUCTS.csv';

proc export data=eduprod.table1
    outfile=outcsv
    dbms=csv
    replace;
run;

/* Export the CAS table to CSV from inside SAS/Viya. */
filename outcsv '/tmp/EDU_ENGAGEMENTS.csv';

proc export data=edugen.table2
    outfile=outcsv
    dbms=csv
    replace;
run;

