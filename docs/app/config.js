// Public settings for the beta app. The anon key is meant to be public: what
// it may read and write is decided by row-level security in the database.
// Never put the service-role key here.
window.JSA_CONFIG = {
  supabaseUrl: "",        // e.g. "https://abcdefgh.supabase.co" (EU region, Frankfurt)
  supabaseAnonKey: "",    // Project settings → API → anon public key
  providers: ["apple", "google"],  // OAuth buttons to show; email link is always there
};
