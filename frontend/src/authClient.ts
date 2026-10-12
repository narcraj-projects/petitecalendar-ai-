import type { SupabaseClient } from "@supabase/supabase-js";

let clientPromise: Promise<SupabaseClient> | undefined;
export function getAuthClient() {
  return (clientPromise ??= (async () => {
    const response = await fetch("/api/auth/config");
    if (!response.ok)
      throw new Error(
        "Sign-in configuration could not be loaded. Refresh to retry.",
      );
    const config = await response.json();
    if (!config.configured)
      throw new Error("Sign-in is awaiting Supabase configuration.");
    const { createClient } = await import("@supabase/supabase-js");
    return createClient(config.supabase_url, config.publishable_key, {
      auth: {
        flowType: "pkce",
        detectSessionInUrl: false,
        persistSession: true,
        autoRefreshToken: true,
      },
    });
  })());
}
