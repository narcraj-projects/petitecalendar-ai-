import { useEffect, useState, type FormEvent } from "react";
import type { Session, SupabaseClient } from "@supabase/supabase-js";
import { CalendarDays, Mail, ShieldCheck, Video } from "lucide-react";
import { getAuthClient } from "./authClient";
import { useLiveRefresh } from "./useLiveRefresh";
import "./guest.css";

type Kind = "upcoming" | "past" | "cancelled";
type Booking = {
  id: string;
  title: string;
  host_name: string;
  host_timezone: string;
  start_at: string;
  end_at: string;
  duration: number;
  invitee_timezone: string;
  status: string;
  location: string;
  meet_url: string | null;
};
type Result = {
  bookings: Booking[];
  has_more: boolean;
  next_offset: number | null;
};
const labels: Record<Kind, string> = {
  upcoming: "Upcoming",
  past: "Past",
  cancelled: "Cancelled",
};
const formatTime = (value: string, timezone: string) =>
  new Intl.DateTimeFormat("en-GB", {
    timeZone: timezone,
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));

export default function GuestDashboard() {
  const [client, setClient] = useState<SupabaseClient>();
  const [session, setSession] = useState<Session | null>(null);
  const [initializing, setInitializing] = useState(true);
  const [email, setEmail] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [kind, setKind] = useState<Kind>("upcoming");
  const [offset, setOffset] = useState(0);
  const [result, setResult] = useState<Result | null>(null);
  const [refresh, setRefresh] = useState(0);
  const live = useLiveRefresh();
  useEffect(() => {
    let active = true;
    let unsubscribe: (() => void) | undefined;
    getAuthClient()
      .then(async (c) => {
        const { data, error } = await c.auth.getSession();
        if (error)
          throw new Error("Sign in again to view your booking history.");
        if (!active) return;
        setClient(c);
        setSession(data.session);
        setInitializing(false);
        const { data: listener } = c.auth.onAuthStateChange((_event, next) => {
          setSession(next);
          setResult(null);
          setOffset(0);
        });
        unsubscribe = () => listener.subscription.unsubscribe();
      })
      .catch(() => {
        if (active) {
          setError("Sign-in could not load. Refresh to try again.");
          setInitializing(false);
        }
      });
    return () => {
      active = false;
      unsubscribe?.();
    };
  }, []);

  useEffect(() => {
    if (!session) return;
    const controller = new AbortController();
    setBusy(true);
    setError("");
    const query = new URLSearchParams({
      kind,
      offset: String(offset),
      limit: "25",
    });
    fetch(`/api/guest/bookings?${query}`, {
      headers: { Authorization: `Bearer ${session.access_token}` },
      signal: controller.signal,
    })
      .then(async (response) => {
        const body = await response.json();
        if (!response.ok) {
          if (response.status === 401) {
            await client?.auth.signOut({ scope: "local" });
            setSession(null);
            setResult(null);
          }
          throw new Error(
            body.error?.message || "Your bookings could not be loaded.",
          );
        }
        if (!controller.signal.aborted) setResult(body);
      })
      .catch((e) => {
        if (!controller.signal.aborted) {
          setResult(null);
          setError(e.message);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setBusy(false);
      });
    return () => controller.abort();
  }, [session?.access_token, kind, offset, refresh, live]);

  async function signIn(event: FormEvent) {
    event.preventDefault();
    if (!client) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      sessionStorage.setItem("petcalendar:auth-destination", "guest");
      const { error } = await client.auth.signInWithOtp({
        email: email.trim(),
        options: {
          shouldCreateUser: true,
          emailRedirectTo: `${window.location.origin}/auth/callback?next=guest`,
        },
      });
      if (error) throw new Error();
      setNotice(
        "Check your inbox for a sign-in link. Open it in this browser to view your bookings.",
      );
    } catch {
      setError(
        "The sign-in link could not be sent. Check your email and try again shortly.",
      );
    } finally {
      setBusy(false);
    }
  }
  function changeKind(next: Kind) {
    setKind(next);
    setOffset(0);
    setResult(null);
  }
  return (
    <div className="guest-shell">
      <header className="guest-header">
        <a className="guest-brand" href="/">
          <CalendarDays size={26} />
          PetiteCalendar-ai
        </a>
        {session ? (
          <button
            onClick={async () => {
              await client?.auth.signOut({ scope: "local" });
              setSession(null);
              setResult(null);
              setNotice("");
              setError("");
            }}
          >
            Sign out
          </button>
        ) : (
          <a href="/login">Host sign in</a>
        )}
      </header>
      <main className="guest-main">
        <p className="guest-eyebrow">YOUR CONVERSATIONS, IN ONE PLACE</p>
        <h1>Your booking history</h1>
        <p className="guest-intro">
          Find your upcoming meetings and revisit past conversations.
        </p>
        {initializing ? (
          <p role="status">Loading your session…</p>
        ) : !session ? (
          <section
            className="guest-signin"
            aria-labelledby="guest-signin-title"
          >
            <ShieldCheck size={30} />
            <h2 id="guest-signin-title">Verify your email</h2>
            <p>
              Use the email address you entered when booking. We’ll send a
              sign-in link before showing any history. You don’t need a host
              profile.
            </p>
            <form onSubmit={signIn}>
              <label htmlFor="history-email">Your booking email</label>
              <input
                id="history-email"
                type="email"
                autoComplete="email"
                required
                maxLength={254}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
              <button className="guest-primary" disabled={!client || busy}>
                <Mail size={19} />
                {busy ? "Sending link…" : "Send sign-in link"}
              </button>
            </form>
            {notice && <p role="status">{notice}</p>}
          </section>
        ) : (
          <>
            <p className="guest-account">Bookings for {session.user.email}</p>
            <div className="guest-toolbar">
              <div
                className="guest-filters"
                role="group"
                aria-label="Booking history filter"
              >
                {(Object.keys(labels) as Kind[]).map((value) => (
                  <button
                    key={value}
                    aria-pressed={kind === value}
                    onClick={() => changeKind(value)}
                  >
                    {labels[value]}
                  </button>
                ))}
              </div>
              <button disabled={busy} onClick={() => setRefresh((v) => v + 1)}>
                Refresh
              </button>
            </div>
            {busy && <p role="status">Updating your bookings…</p>}
            {!busy && result?.bookings.length === 0 && (
              <section className="guest-empty">
                <CalendarDays size={30} />
                <h2>No {kind} bookings</h2>
                <p>
                  Bookings made with this verified email will appear here. To
                  book a new meeting, open the link shared by your host.
                </p>
              </section>
            )}
            <div className="guest-bookings">
              {result?.bookings.map((booking) => (
                <article key={booking.id} className="guest-booking">
                  <div className="guest-booking-heading">
                    <h2>{booking.title}</h2>
                    <span>
                      {booking.status === "cancelled"
                        ? "Cancelled"
                        : kind === "past"
                          ? "Completed"
                          : "Confirmed"}
                    </span>
                  </div>
                  <p>
                    With {booking.host_name} · {booking.duration} minutes
                  </p>
                  <div className="guest-zones">
                    <div>
                      <strong>Your booking time</strong>
                      <p>
                        {formatTime(booking.start_at, booking.invitee_timezone)}
                      </p>
                      <small>{booking.invitee_timezone}</small>
                    </div>
                    <div>
                      <strong>Host time</strong>
                      <p>
                        {formatTime(booking.start_at, booking.host_timezone)}
                      </p>
                      <small>{booking.host_timezone}</small>
                    </div>
                  </div>
                  {booking.meet_url && kind === "upcoming" ? (
                    <a
                      className="guest-meet"
                      href={booking.meet_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <Video size={18} />
                      Join Google Meet
                    </a>
                  ) : (
                    <p>{booking.location}</p>
                  )}
                  <p className="guest-manage-note">
                    To manage this booking, use the private link in your
                    original confirmation email.
                  </p>
                </article>
              ))}
            </div>
            <div className="guest-pagination">
              {offset > 0 && (
                <button
                  disabled={busy}
                  onClick={() => setOffset((v) => Math.max(0, v - 25))}
                >
                  Previous bookings
                </button>
              )}
              {result?.has_more && (
                <button
                  disabled={busy}
                  onClick={() => setOffset(result.next_offset!)}
                >
                  More bookings
                </button>
              )}
            </div>
          </>
        )}
        {error && <p role="alert">{error}</p>}
        <a className="guest-home" href="/">
          Back to booking links
        </a>
      </main>
    </div>
  );
}
