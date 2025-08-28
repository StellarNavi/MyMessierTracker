CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS citext;

-- main table for user info ***************************************************************************
CREATE TABLE public.users (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  email CITEXT NOT NULL UNIQUE,
  user_name TEXT NOT NULL,
  verified_email BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- main Messier objects table *************************************************************************
CREATE TABLE public.messier_objects (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  messier_number INT NOT NULL UNIQUE CHECK (messier_number BETWEEN 1 AND 110),
  common_name TEXT,
  object_type TEXT,
  constellation TEXT,
  ra_hours NUMERIC(6,3),
  dec_degrees NUMERIC(6,3),
  magnitude NUMERIC(4,2),
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Images table ***************************************************************************************
CREATE TABLE public.images (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  storage_url TEXT NOT NULL,
  thumbnail_url TEXT,
  mime_type TEXT,
  byte_size BIGINT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Link between user and Messier object (only one active image allowed) ******************************
CREATE TABLE public.user_object_images (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  messier_id UUID NOT NULL REFERENCES public.messier_objects(id),
  image_id UUID NOT NULL REFERENCES public.images(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uoi_user_object_unique UNIQUE (user_id, messier_id) --unique user/object image enforced
);

-- best practice to create indexes for these values that will be queried often
CREATE INDEX uoi_user_idx ON public.user_object_images(user_id);
CREATE INDEX uoi_messier_idx ON public.user_object_images(messier_id);

-- Journal entries ***********************************************************************************
CREATE TABLE public.journal_entries (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  messier_id UUID NOT NULL REFERENCES public.messier_objects(id), -- no need for cascase here, static
  image_id UUID REFERENCES public.images(id) ON DELETE CASCADE,
  body VARCHAR(500) not null ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -- create later a view for tracking user progress (main page analytics)
-- CREATE OR REPLACE VIEW public.v_user_progress AS
-- SELECT
--   u.id AS user_id,
--   COUNT(DISTINCT uoi.messier_id) AS objects_completed
-- FROM public.messier_objects m
-- LEFT JOIN public.users u
--   ON uoi.user_id = u.id AND uoi.is_active
-- GROUP BY u.id;
