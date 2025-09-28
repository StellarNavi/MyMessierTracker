-- this file will tell docker how to generate the database
-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS citext;



-- MESSIER OBJECTS -------------------------------------------------------------
  -- purpose: main table that stores data pertaining to the messier objects like the
  -- Messier number, the type, location, etc
CREATE TABLE IF NOT EXISTS public.messier_objects (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  messier_number INT NOT NULL UNIQUE CHECK (messier_number BETWEEN 1 AND 110),
  common_name   TEXT,
  object_type   TEXT,          
  constellation TEXT,
  ra_hours      NUMERIC(6,3),
  dec_degrees   NUMERIC(6,3),
  magnitude     NUMERIC(4,2),
  notes         TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  distance_ly NUMERIC,
  object_subtype TEXT,        
  url           TEXT          
);

-- USERS -----------------------------------------------------------------------
  -- purpose: stores one record per registered user of the Messier Tracker App and 
  -- acts as the core identity table for other tables to connect user data to. For 
  -- example many other tables will have a FK for a user such as images, progress 
  -- and journal entries.
CREATE TABLE IF NOT EXISTS public.users (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  email CITEXT NOT NULL UNIQUE,
  user_name TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  verified_email BOOLEAN NOT NULL DEFAULT FALSE, --remove
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- IMAGES ----------------------------------------------------------------------
  -- purpose: stores all information for images uploaded by users with metadata, 
  -- audit fields like when it was logged, etc. It does not directly include
  -- messier object tags as that will be a separate table
CREATE TABLE IF NOT EXISTS public.images (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id   UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  file_name TEXT NOT NULL,
  file_path TEXT NOT NULL, 
  mime_type TEXT,
  byte_size BIGINT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- USER OBJECT IMAGE (one image per user per object) --------------------------------
  -- purpose: bridges the uploaded messier image with the information of the user who 
  -- uploaded it. uoi_user_object_unique  will help ensure that only one image per 
  -- object per user, preventing redundant data and keeping the app fast and uncluttered
  --  as it grows (it will also help with error handling).
CREATE TABLE IF NOT EXISTS public.user_object_images (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id    UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  messier_id UUID NOT NULL REFERENCES public.messier_objects(id) ON DELETE CASCADE,
  image_id   UUID     REFERENCES public.images(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uoi_user_object_unique UNIQUE (user_id, messier_id)
);

-- INDEXES
  -- inedxes are good practice and will help with more efficient joins and the
  -- per-user/per-object lookups
CREATE INDEX IF NOT EXISTS uoi_user_idx    ON public.user_object_images(user_id);
CREATE INDEX IF NOT EXISTS uoi_messier_idx ON public.user_object_images(messier_id);

-- USER JOURNAL ENTRIES -------------------------------------------------------------
  -- purpose: stores user notes pertaining to the messier objects they have loaded to 
  -- the app. it allows the user to capture any additional detail such as imaging 
  -- session length and other details or even personal commentary. 
CREATE TABLE IF NOT EXISTS public.journal_entries (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id    UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  messier_id UUID NOT NULL REFERENCES public.messier_objects(id) ON DELETE CASCADE,
  image_id   UUID     REFERENCES public.images(id) ON DELETE SET NULL,
  body       TEXT,
  observed_date DATE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT journal_entries_user_object_unique UNIQUE (user_id, messier_id)
);

CREATE INDEX IF NOT EXISTS idx_je_user ON public.journal_entries(user_id);
CREATE INDEX IF NOT EXISTS idx_je_obj  ON public.journal_entries(messier_id);

-- ENHANCEMENT 2: implement a rarity score and use it to show the top remaining items 
create or replace view public.v_object_rarity as
with total_users as ( -- this is the denominator: a count of all registered users
    select count(*)::numeric as total_users
    from public.users),
     obj as ( -- this is the numerator: a distinct count of users who have captured each object
         select mo.id                                as messier_id,
                mo.messier_number,
                mo.common_name,
                mo.object_type,
                count(distinct uoi.user_id)::numeric as user_ct
         from public.messier_objects mo
                  left join public.user_object_images uoi
                            on uoi.messier_id = mo.id
         group by mo.id, mo.messier_number, mo.common_name)
-- final query calculates the rarity per object
select o.messier_id,
       o.object_type,
       o.messier_number || ': ' || o.common_name as object,
       -- gets the % val that can be used downstream to sort and limit by but also append
       -- a '%' sign to and make sense to the user
       case
           when t.total_users = 0 then 0
           else round(100 * o.user_ct / t.total_users, 0) end as rarity_pct
from obj o
         cross join total_users t
order by rarity_pct desc;