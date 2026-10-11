import { useEffect, useState } from "react";
import { CalendarDays, ShieldCheck } from "lucide-react";
import HostNavigation from "./components/HostNavigation";
import "./events.css";
import "./integrations.css";
type Connection = {
  status: string;
  revision: number;
  blocking_ids: string[];
  destination_id: string | null;
  create_meet: boolean;
};
type Calendar = {
  id: string;
  name: string;
  writable: boolean;
  meet_supported: boolean;
  primary: boolean;
};
type Data = {
  configured: boolean;
  connection: Connection;
  calendars: Calendar[];
};
const callbackResult = new URLSearchParams(window.location.search).get(
  "calendar",
);
const callbackErrors: Record<string, string> = {
  calendar_access_failed:
    "Google consent succeeded, but calendars could not be read. Check that Google Calendar API is enabled and all Calendar permissions are allowed, then reconnect.",
  consent_expired:
    "Calendar consent expired or lost its browser cookie. Connect again in this browser.",
  consent_incomplete:
    "Google did not grant all Calendar permissions. Connect again and allow every requested permission.",
  client_configuration:
    "Google rejected the Calendar client credentials. The server needs the matching client ID, secret and callback URL.",
  authorization_failed:
    "Google could not exchange Calendar consent. Start a fresh connection; if it repeats, check the Calendar client credentials.",
  storage_unavailable:
    "Calendar consent could not be saved. Retry the connection when storage is available.",
};
if (window.location.pathname === "/app/integrations" && callbackResult)
  window.history.replaceState({}, "", window.location.pathname);
export default function Integrations({
  profile,
  request,
  signOut,
}: {
  profile: { display_name: string; timezone: string };
  request: (url: string, options?: RequestInit) => Promise<any>;
  signOut: () => void;
}) {
  const [data, setData] = useState<Data>(),
    [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [notice, setNotice] = useState(
    callbackResult === "connected"
      ? "Google connected. Choose your calendars and save below."
      : callbackResult === "denied"
        ? "Calendar access was declined. You can connect when ready."
        : callbackResult && callbackErrors[callbackResult]
          ? callbackErrors[callbackResult]
          : callbackResult === "failed"
            ? "Calendar connection could not finish. Try connecting again."
            : "",
  );
  const [blocking, setBlocking] = useState<string[]>([]),
    [destination, setDestination] = useState(""),
    [meet, setMeet] = useState(true);
  async function load() {
    setLoading(true);
    setError("");
    try {
      const d: Data = await request("/api/me/integrations/google");
      setData(d);
      setBlocking(d.connection.blocking_ids);
      setDestination(d.connection.destination_id || "");
      setMeet(d.connection.create_meet);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void load();
  }, []);
  async function connect() {
    setBusy(true);
    setError("");
    try {
      const body = await request("/api/me/integrations/google/connect", {
        method: "POST",
      });
      window.location.assign(body.authorization_url);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }
  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!data) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const body = await request("/api/me/integrations/google", {
        method: "PUT",
        body: JSON.stringify({
          revision: data.connection.revision,
          blocking_ids: blocking,
          destination_id: destination,
          create_meet: meet,
        }),
      });
      setData({ ...data, connection: body.connection });
      setBlocking(body.connection.blocking_ids);
      setNotice(
        "Calendar settings saved. New bookings will sync to your chosen calendar.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function disconnect() {
    if (!data) return;
    setBusy(true);
    setError("");
    try {
      const body = await request("/api/me/integrations/google/disconnect", {
        method: "POST",
        body: JSON.stringify({ revision: data.connection.revision }),
      });
      setData({ ...data, connection: body.connection, calendars: [] });
      setBlocking([]);
      setDestination("");
      setNotice(
        body.google_revoked
          ? "Google Calendar disconnected and access revoked."
          : "Google Calendar disconnected locally. You can also remove access in your Google account settings.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="events-shell">
      <HostNavigation
        current="integrations"
        profile={profile}
        signOut={signOut}
      />
      <main className="events-main">
        <span className="event-eyebrow">YOUR CONNECTED SERVICES</span>
        <h1>Calendar & Meet</h1>
        <section className="event-card integration-intro">
          <CalendarDays size={28} />
          <h2>Google Calendar</h2>
          <p>
            Choose the calendars that protect your time and the calendar where
            new bookings appear. Connect with separate Google permission.
          </p>
          <div className="event-guard">
            <ShieldCheck size={20} />
            <p>
              We check busy intervals in your selected calendars. Your calendar
              contents are never shown on the public booking page.
            </p>
          </div>
          <p>
            New bookings stay reserved while calendar delivery retries. Meet
            links appear on the private confirmation page after Google creates
            them.
          </p>
          <button
            className="event-primary"
            disabled={busy || loading || data?.configured === false}
            onClick={() => void connect()}
          >
            {busy
              ? "Working…"
              : data?.connection.status === "connected"
                ? "Reconnect Google Calendar"
                : "Connect Google Calendar"}
          </button>
          {data?.configured === false && (
            <p>Calendar connection is awaiting setup.</p>
          )}
        </section>
        {loading && <p role="status">Loading calendar connection…</p>}
        {error && (
          <div className="event-error" role="alert">
            {error}
            <button
              className="event-secondary"
              disabled={busy}
              onClick={() => void load()}
            >
              Reload connection
            </button>
          </div>
        )}
        {notice && (
          <p role="status" className="integration-notice">
            {notice}
          </p>
        )}
        {!loading && data?.connection.status === "connected" && (
          <form className="event-card integration-form" onSubmit={save}>
            <h2>Choose your calendars</h2>
            <fieldset disabled={busy}>
              <legend>Calendars that block available times</legend>
              {data.calendars.map((c) => (
                <label className="integration-check" key={c.id}>
                  <input
                    type="checkbox"
                    checked={blocking.includes(c.id) || destination === c.id}
                    disabled={destination === c.id}
                    onChange={(e) =>
                      setBlocking(
                        e.target.checked
                          ? [...blocking, c.id]
                          : blocking.filter((id) => id !== c.id),
                      )
                    }
                  />
                  <span>
                    {c.name}
                    {c.primary ? " · Primary" : ""}
                    <small>{c.writable ? "Writable" : "Read only"}</small>
                  </span>
                </label>
              ))}
              <p>
                Your destination calendar is always included in busy checks.
                Caps count PetiteCalendar-ai bookings; external busy periods
                protect time.
              </p>
              <label htmlFor="calendar-destination">
                Destination for new bookings
              </label>
              <select
                id="calendar-destination"
                required
                value={destination}
                onChange={(e) => setDestination(e.target.value)}
              >
                <option value="">Choose a writable calendar</option>
                {data.calendars
                  .filter((c) => c.writable)
                  .map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
              </select>
              <label className="integration-check">
                <input
                  type="checkbox"
                  checked={meet}
                  onChange={(e) => setMeet(e.target.checked)}
                />
                <span>Create a Google Meet link for new bookings</span>
              </label>
              <p>
                Choose a Meet-compatible destination when this is enabled.
                Existing bookings retain their original delivery destination.
              </p>
              <button className="event-primary" disabled={busy}>
                {busy ? "Saving…" : "Save calendar settings"}
              </button>
            </fieldset>
          </form>
        )}
        {!loading &&
          data &&
          data.connection.status !== "not_connected" &&
          data.connection.status !== "disconnected" && (
            <section className="event-card">
              <h2>Disconnect calendar access</h2>
              <p>
                This stops future calendar checks and delivery. Existing Google
                events and PetiteCalendar-ai reservations remain saved.
              </p>
              <button
                className="event-secondary"
                disabled={busy}
                onClick={() => void disconnect()}
              >
                Disconnect Google Calendar
              </button>
            </section>
          )}
        <section className="event-card">
          <h2>Delivery details</h2>
          <p>
            New bookings made after calendar settings are saved are sent to your
            destination. Earlier bookings remain as they were. Host calendar
            events contain no guest invitation. Email confirmations are sent
            separately when enabled, and private booking pages offer calendar
            downloads.
          </p>
          <a href="/app/bookings">See booking delivery statuses</a>
        </section>
      </main>
    </div>
  );
}
