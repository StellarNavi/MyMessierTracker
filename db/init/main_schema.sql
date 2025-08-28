-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS citext;



-- MESSIER OBJECTS -------------------------------------------------------------
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
CREATE TABLE IF NOT EXISTS public.users (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  email CITEXT NOT NULL UNIQUE,
  user_name TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  verified_email BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- IMAGES ----------------------------------------------------------------------
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
CREATE TABLE IF NOT EXISTS public.user_object_images (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id    UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  messier_id UUID NOT NULL REFERENCES public.messier_objects(id) ON DELETE CASCADE,
  image_id   UUID     REFERENCES public.images(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uoi_user_object_unique UNIQUE (user_id, messier_id)
);

CREATE INDEX IF NOT EXISTS uoi_user_idx    ON public.user_object_images(user_id);
CREATE INDEX IF NOT EXISTS uoi_messier_idx ON public.user_object_images(messier_id);

-- USER JKOURNAL ENTRIES -------------------------------------------------------------
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
