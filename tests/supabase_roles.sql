-- Local integration-test scaffolding only. Supabase already provides these roles/schema.
create role anon nologin;
create role authenticated nologin;
create role service_role nologin bypassrls;
create schema storage;
create table storage.buckets(id text primary key,name text,public boolean,file_size_limit bigint,allowed_mime_types text[]);
