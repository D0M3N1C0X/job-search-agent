"""The online beta: a Supabase-backed service around the same engine.

`rest` talks to Supabase with the standard library; `worker` runs the engine
for every member. The browser app lives in web/, the database in
cloud/supabase/.
"""
