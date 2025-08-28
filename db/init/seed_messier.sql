-- seed the messier objects table with data from the csv file

TRUNCATE TABLE public.messier_objects RESTART IDENTITY CASCADE;

COPY public.messier_objects
  (id,
   messier_number,
   common_name,
   object_type,
   constellation,
   ra_hours,
   dec_degrees,
   magnitude,
   notes,
   created_at,
   updated_at,
   distance_ly,
   object_subtype,
   url)
FROM '/docker-entrypoint-initdb.d/messier_objects.csv'
WITH (FORMAT csv, HEADER true);
