-- Migration: 003_outlook_integration.sql
-- Adds support for Microsoft Outlook / 365 integration alongside Gmail

-- 1. Outlook Connection Table
create table if not exists outlook_connections (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade,
  outlook_address text not null,
  refresh_token text not null,
  is_active boolean default true,
  connected_at timestamptz default now()
);

-- 2. Modify emails table for multi-provider support
-- Drop not null on gmail_message_id to allow emails from Outlook
alter table emails alter column gmail_message_id drop not null;

-- Add provider identifier and Outlook-specific IDs
alter table emails add column if not exists provider text default 'gmail';
alter table emails add column if not exists outlook_message_id text unique;
alter table emails add column if not exists outlook_conversation_id text;

-- 3. Modify email_drafts table to record sent draft id for Outlook
alter table email_drafts add column if not exists outlook_message_id text;
