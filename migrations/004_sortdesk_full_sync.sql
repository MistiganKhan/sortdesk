-- =========================================================================
-- Migration 004: SortDesk Full Schema Sync
-- Copy and run this script in your Supabase SQL Editor:
-- Dashboard -> SQL Editor -> New query -> Paste & Run
-- =========================================================================

-- 1. Users Table (Auth, passwords, workspaces)
ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS company_name text DEFAULT 'SortDesk Agency',
  ADD COLUMN IF NOT EXISTS password_hash text;

-- 2. Emails Table (Multi-provider support: Gmail & Outlook)
ALTER TABLE public.emails
  ALTER COLUMN gmail_message_id DROP NOT NULL;

ALTER TABLE public.emails
  ADD COLUMN IF NOT EXISTS provider text DEFAULT 'gmail',
  ADD COLUMN IF NOT EXISTS outlook_message_id text,
  ADD COLUMN IF NOT EXISTS outlook_conversation_id text;

-- 3. Email Drafts Table (Multi-provider draft tracking)
ALTER TABLE public.email_drafts
  ADD COLUMN IF NOT EXISTS outlook_message_id text;

-- 4. Email Categories Table (Priority detection)
ALTER TABLE public.email_categories
  ADD COLUMN IF NOT EXISTS priority text DEFAULT 'Medium',
  ADD COLUMN IF NOT EXISTS priority_reason text;

-- 5. Outlook Connections Table
CREATE TABLE IF NOT EXISTS public.outlook_connections (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES public.users(id) ON DELETE CASCADE,
  outlook_address text NOT NULL,
  refresh_token text NOT NULL,
  is_active boolean DEFAULT true,
  connected_at timestamptz DEFAULT now()
);

-- 6. Refresh Tokens Table (JWT session security & token rotation)
CREATE TABLE IF NOT EXISTS public.refresh_tokens (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  token_hash text NOT NULL UNIQUE,
  issued_at timestamptz DEFAULT now(),
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  replaced_by uuid,
  user_agent text,
  ip_address text,
  CONSTRAINT refresh_tokens_pkey PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON public.refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_token_hash ON public.refresh_tokens(token_hash);
