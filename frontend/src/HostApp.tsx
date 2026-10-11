import { useEffect, useState } from "react";
import { type Session, type SupabaseClient } from "@supabase/supabase-js";
import { ArrowRight, CalendarDays, Globe, ShieldCheck } from "lucide-react";
import "./host.css";
import EventTypes from "./EventTypes";
import AvailabilitySettings from "./AvailabilitySettings";
import BookingsDashboard from "./BookingsDashboard";
import Integrations from "./Integrations";
import { getAuthClient } from "./authClient";

type Profile = { display_name: string; username: string; timezone: string };
const path = window.location.pathname;
const callback = new URLSearchParams(window.location.search);
if (path === "/auth/callback") window.history.replaceState({}, "", path);
let initialization:
  Promise<{ client: SupabaseClient; session: Session | null }> | undefined;
function initialize() {
  return (initialization ??= (async () => {
    const client = await getAuthClient();
    if (path === "/auth/callback") {
      const code = callback.get("code");
      const tokenHash = callback.get("token_hash");
      if (callback.has("error") || (!code && !tokenHash))
        throw new Error("This sign-in link is invalid. Request a new link.");
      const result = code
        ? await client.auth.exchangeCodeForSession(code)
        : await client.auth.verifyOtp({
            token_hash: tokenHash!,
            type: "email",
          });
      if (result.error)
        throw new Error(
          "This sign-in link expired or could not be verified. Request a new link in the same browser.",
        );
    }
    const { data, error } = await client.auth.getSession();
    if (error)
      throw new Error("Your session could not be loaded. Sign in again.");
    return { client, session: data.session };
  })());
}
const steps = ["Your name", "Booking username", "Home timezone", "Review"];
const deviceZone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
const zones = Array.from(
  new Set([deviceZone, "UTC", ...Intl.supportedValuesOf("timeZone")]),
).sort();

export default function HostApp() {
  const [client, setClient] = useState<SupabaseClient>();
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [form, setForm] = useState<Profile>({
    display_name: "",
    username: "",
    timezone: deviceZone,
  });
  const [step, setStep] = useState(0);
  const [editing, setEditing] = useState(path === "/onboarding");
  useEffect(() => {
    let active = true;
    let unsubscribe: (() => void) | undefined;
    initialize()
      .then(({ client: c, session: s }) => {
        if (!active) return;
        setClient(c);
        setSession(s);
        setLoading(false);
        const { data } = c.auth.onAuthStateChange((_event, next) =>
          setSession(next),
        );
        unsubscribe = () => data.subscription.unsubscribe();
        if (path !== "/login" && !s) window.location.replace("/login");
        if (path === "/auth/callback" && s)
          window.location.replace("/onboarding");
        if (path === "/login" && s) window.location.replace("/app/profile");
      })
      .catch((e) => {
        if (active) {
          setError(e.message);
          setLoading(false);
        }
      });
    return () => {
      active = false;
      unsubscribe?.();
    };
  }, []);

  async function request(url: string, options: RequestInit = {}) {
    const result = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${session?.access_token}`,
        ...options.headers,
      },
    });
    const body = await result.json();
    if (result.status === 401) {
      await client?.auth.signOut({ scope: "local" });
      window.location.replace("/login");
    }
    if (!result.ok) {
      const error = Object.assign(
        new Error(body.error?.message || "The request failed. Try again."),
        { status: result.status },
      );
      throw error;
    }
    return body;
  }
  async function loadProfile() {
    setLoading(true);
    setError("");
    try {
      const body = await request("/api/me");
      setProfile(body.profile);
      if (body.profile) setForm(body.profile);
      else setEditing(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    if (session && path !== "/login" && path !== "/auth/callback")
      void loadProfile();
  }, [session?.access_token]);

  async function signIn(kind: "email" | "google") {
    if (!client) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const redirectTo = `${window.location.origin}/auth/callback`;
      const result =
        kind === "google"
          ? await client.auth.signInWithOAuth({
              provider: "google",
              options: { redirectTo },
            })
          : await client.auth.signInWithOtp({
              email: email.trim(),
              options: { emailRedirectTo: redirectTo, shouldCreateUser: true },
            });
      if (result.error)
        throw new Error(
          kind === "google"
            ? "Google sign-in could not start. Check that the provider is configured, or use email."
            : "The sign-in link could not be sent. Check your email and try again shortly.",
        );
      if (kind === "email")
        setNotice(
          "Check your inbox for a sign-in link. Open it in this browser.",
        );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function next() {
    setError("");
    if (
      step === 0 &&
      (form.display_name.trim().length < 2 ||
        form.display_name.trim().length > 80)
    )
      return setError("Enter a name with 2–80 characters.");
    if (
      step === 1 &&
      (!/^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/.test(form.username) ||
        form.username.length < 3 ||
        form.username.length > 32)
    )
      return setError(
        "Use 3–32 lowercase letters, numbers or single hyphens. Start with a letter.",
      );
    setStep(step + 1);
  }
  async function save() {
    setBusy(true);
    setError("");
    try {
      const { profile: saved } = await request("/api/me/profile", {
        method: "PUT",
        body: JSON.stringify({
          display_name: form.display_name.trim(),
          username: form.username,
          timezone: form.timezone,
        }),
      });
      setProfile(saved);
      setEditing(false);
      setNotice("Your profile is saved.");
      window.history.replaceState({}, "", "/app/profile");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const login = path === "/login";
  if (path === "/app/integrations" && session && profile && !loading) {
    return (
      <Integrations
        profile={profile}
        request={request}
        signOut={() =>
          void client?.auth
            .signOut({ scope: "local" })
            .then(() => window.location.replace("/login"))
        }
      />
    );
  }
  if (
    (path === "/app/bookings" || path === "/app") &&
    session &&
    profile &&
    !loading
  ) {
    return (
      <BookingsDashboard
        profile={profile}
        request={request}
        signOut={() =>
          void client?.auth
            .signOut({ scope: "local" })
            .then(() => window.location.replace("/login"))
        }
      />
    );
  }
  if (path === "/app/availability" && session && profile && !loading) {
    return (
      <AvailabilitySettings
        profile={profile}
        request={request}
        signOut={() =>
          void client?.auth
            .signOut({ scope: "local" })
            .then(() => window.location.replace("/login"))
        }
      />
    );
  }
  if (path.startsWith("/app/event-types") && session && profile && !loading) {
    return (
      <EventTypes
        profile={profile}
        request={request}
        signOut={() =>
          void client?.auth
            .signOut({ scope: "local" })
            .then(() => window.location.replace("/login"))
        }
      />
    );
  }
  return (
    <div className="host-shell">
      <header className="host-header">
        <a href="/ananya/career-strategy" className="host-brand">
          <CalendarDays size={24} /> PetCalendar AI
        </a>
        <a href="/ananya/career-strategy">
          Availability demo <ArrowRight size={16} />
        </a>
      </header>
      <main className="host-layout">
        <aside className="host-intro">
          <span className="host-eyebrow">YOUR CALENDAR, WITH INTENTION</span>
          <h1>
            {login
              ? "Make room for what matters."
              : "A little setup. A better calendar."}
          </h1>
          <p>
            Start with your host profile. Your booking pages and availability
            settings follow next.
          </p>
          <div className="host-protection">
            <ShieldCheck size={22} />
            <div>
              <strong>Built around your time</strong>
              <p>
                Your home timezone anchors your schedule. Invitees can choose
                their current travel timezone.
              </p>
            </div>
          </div>
        </aside>
        <section
          className="host-card"
          aria-label={login ? "Host sign in" : "Host profile"}
        >
          {loading ? (
            <p role="status">
              {login ? "Preparing sign-in…" : "Loading your profile…"}
            </p>
          ) : login ? (
            <>
              <span className="host-eyebrow">WELCOME TO PETCALENDAR AI</span>
              <h2>Sign in as a host</h2>
              <p>Use Google or get a secure link by email.</p>
              <button
                className="host-secondary"
                disabled={!client || busy}
                onClick={() => void signIn("google")}
              >
                Continue with Google
              </button>
              <div className="host-divider">or use email</div>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void signIn("email");
                }}
              >
                <label htmlFor="email">Email address</label>
                <input
                  id="email"
                  type="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={busy}
                />
                <button className="host-primary" disabled={!client || busy}>
                  {busy ? "Please wait…" : "Email me a sign-in link"}
                  <ArrowRight size={18} />
                </button>
              </form>
              <p className="host-small">
                No password to remember. Google calendar access is configured
                separately later.
              </p>
            </>
          ) : session && editing ? (
            <>
              <span className="host-eyebrow">STEP {step + 1} OF 4</span>
              <h2>{steps[step]}</h2>
              <ol className="host-steps">
                {steps.map((name, i) => (
                  <li
                    key={name}
                    aria-current={i === step ? "step" : undefined}
                    className={i <= step ? "reached" : ""}
                  >
                    <span>{i + 1}</span>
                    <small>{name}</small>
                  </li>
                ))}
              </ol>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void (step === 3 ? save() : next());
                }}
              >
                {step === 0 && (
                  <>
                    <label htmlFor="display-name">Display name</label>
                    <input
                      autoFocus
                      id="display-name"
                      value={form.display_name}
                      maxLength={80}
                      autoComplete="name"
                      onChange={(e) =>
                        setForm({ ...form, display_name: e.target.value })
                      }
                    />
                    <p>The name invitees will see on your booking page.</p>
                  </>
                )}
                {step === 1 && (
                  <>
                    <label htmlFor="username">Booking username</label>
                    <input
                      autoFocus
                      id="username"
                      value={form.username}
                      maxLength={32}
                      autoCapitalize="none"
                      spellCheck={false}
                      onChange={(e) =>
                        setForm({
                          ...form,
                          username: e.target.value.toLowerCase(),
                        })
                      }
                    />
                    <p>
                      Use lowercase letters, numbers and single hyphens. Your
                      username must be unique.
                    </p>
                    <div className="host-link-preview">
                      /{form.username || "your-name"}/event-name
                    </div>
                  </>
                )}
                {step === 2 && (
                  <>
                    <label htmlFor="home-zone">Home timezone</label>
                    <select
                      autoFocus
                      id="home-zone"
                      value={form.timezone}
                      onChange={(e) =>
                        setForm({ ...form, timezone: e.target.value })
                      }
                    >
                      {zones.map((zone) => (
                        <option key={zone}>{zone}</option>
                      ))}
                    </select>
                    <p>
                      <Globe size={16} /> Initially suggested by your device.
                      Confirm the timezone you want to use for your host
                      schedule.
                    </p>
                    <p>
                      This is separate from an invitee’s current or travel
                      timezone.
                    </p>
                  </>
                )}
                {step === 3 && (
                  <>
                    <p>
                      Confirm these details before saving your host profile.
                    </p>
                    <ProfileSummary profile={form} />
                    <p className="host-small">
                      This saves your profile. Your booking link becomes
                      available after you publish an event type.
                    </p>
                  </>
                )}
                <div className="host-actions">
                  {step > 0 && (
                    <button
                      type="button"
                      className="host-secondary"
                      disabled={busy}
                      onClick={() => {
                        setStep(step - 1);
                        setError("");
                      }}
                    >
                      Back
                    </button>
                  )}
                  <button className="host-primary" disabled={busy}>
                    {busy
                      ? "Saving…"
                      : step === 3
                        ? "Confirm & save profile"
                        : "Continue"}
                    <ArrowRight size={18} />
                  </button>
                </div>
              </form>
              <button
                className="host-text-button"
                onClick={() =>
                  void client?.auth
                    .signOut({ scope: "local" })
                    .then(() => window.location.replace("/login"))
                }
              >
                Sign out
              </button>
            </>
          ) : session && profile ? (
            <>
              <span className="host-eyebrow">HOST PROFILE</span>
              <h2>You’re ready, {profile.display_name}.</h2>
              <ProfileSummary profile={profile} />
              <div className="host-protection">
                <ShieldCheck size={22} />
                <p>
                  Your profile is saved. Create an event type to offer your
                  first conversation.
                </p>
              </div>
              <a className="host-primary" href="/app/event-types">
                Manage event types <ArrowRight size={18} />
              </a>
              <button
                className="host-primary"
                onClick={() => {
                  setEditing(true);
                  setStep(0);
                  setNotice("");
                }}
              >
                Edit profile
              </button>
              <button
                className="host-secondary"
                onClick={() =>
                  void client?.auth
                    .signOut({ scope: "local" })
                    .then(() => window.location.replace("/login"))
                }
              >
                Sign out
              </button>
            </>
          ) : (
            <>
              <h2>
                {session ? "Profile unavailable" : "Sign-in could not finish"}
              </h2>
              {!session && <a href="/login">Return to sign in</a>}
            </>
          )}
          {error && (
            <div role="alert" className="host-error">
              {error}
              {session && !editing && (
                <button
                  className="host-secondary"
                  onClick={() => void loadProfile()}
                >
                  Retry
                </button>
              )}
            </div>
          )}
          {notice && (
            <p role="status" className="host-notice">
              {notice}
            </p>
          )}
        </section>
      </main>
    </div>
  );
}
function ProfileSummary({ profile }: { profile: Profile }) {
  return (
    <dl className="host-summary">
      <div>
        <dt>Display name</dt>
        <dd>{profile.display_name}</dd>
      </div>
      <div>
        <dt>Booking username</dt>
        <dd>{profile.username}</dd>
      </div>
      <div>
        <dt>Home timezone</dt>
        <dd>{profile.timezone}</dd>
      </div>
    </dl>
  );
}
