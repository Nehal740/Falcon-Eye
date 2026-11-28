-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- (Falcon Eye also does this automatically at start-up; this file is the manual backup.)
-- Falcon Eye connects directly to the database, so it does not need Supabase's public REST API.
DO $$
DECLARE t record;
BEGIN
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t.tablename);
  END LOOP;
END $$;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
