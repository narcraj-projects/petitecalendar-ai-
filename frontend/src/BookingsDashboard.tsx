import { useEffect, useState } from "react";
import HostNavigation from "./components/HostNavigation";
import { bookingTime, type SavedBooking } from "./BookingConfirmation";
import "./events.css";
import "./bookings.css";
import CalendarDelivery from "./components/CalendarDelivery";
import EmailDelivery from "./components/EmailDelivery";
import BookingManagement from "./components/BookingManagement";
import { useLiveRefresh } from "./useLiveRefresh";
export default function BookingsDashboard({
  profile,
  request,
  signOut,
}: {
  profile: { display_name: string; timezone: string };
  request: (url: string, options?: RequestInit) => Promise<any>;
  signOut: () => void;
}) {
  const refresh = useLiveRefresh();
  const [refreshError, setRefreshError] = useState("");
  const [month, setMonth] = useState(
    new Date(new Date().getFullYear(), new Date().getMonth(), 1),
  );
  const [data, setData] = useState<{
    bookings: SavedBooking[];
    week_bookings: SavedBooking[];
    week_start: string;
    truncated: boolean;
    schedule: {
      timezone: string;
      host_daily_cap: number;
      weekly_cap_minutes: number;
    } | null;
  }>();
  const [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [retry, setRetry] = useState(0),
    [filter, setFilter] = useState("upcoming");
  useEffect(() => {
    let active = true;
    if (!data) setLoading(true);
    setError("");
    const end = new Date(month.getFullYear(), month.getMonth() + 1, 1);
    const q = new URLSearchParams({
      start: `${month.getFullYear()}-${String(month.getMonth() + 1).padStart(2, "0")}-01`,
      end: `${end.getFullYear()}-${String(end.getMonth() + 1).padStart(2, "0")}-01`,
    });
    request(`/api/me/bookings?${q}`)
      .then((d) => {
        if (active) {
          setData(d);
          setRefreshError("");
        }
      })
      .catch((e) => {
        if (active) {
          if (data)
            setRefreshError(
              "Updates could not be loaded. Retrying automatically.",
            );
          else setError(e.message);
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [month, retry, refresh]);
  const zone = data?.schedule?.timezone || profile.timezone;
  const now = new Date();
  const localKey = (d: Date) =>
    new Intl.DateTimeFormat("en-CA", {
      timeZone: zone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(d);
  const monday = data?.week_start || localKey(now);
  const weekKeys = Array.from({ length: 7 }, (_, i) =>
    new Date(new Date(`${monday}T12:00:00Z`).getTime() + i * 86400000)
      .toISOString()
      .slice(0, 10),
  );
  const weekRows =
    data?.week_bookings.filter((b) =>
      weekKeys.includes(localKey(new Date(b.start_at))),
    ) || [];
  const rows =
    data?.bookings.filter((b) =>
      filter === "cancelled"
        ? b.status === "cancelled"
        : b.status !== "cancelled" &&
          (filter === "upcoming"
            ? new Date(b.end_at) > now
            : new Date(b.end_at) <= now),
    ) || [];
  return (
    <div className="events-shell">
      <HostNavigation current="bookings" profile={profile} signOut={signOut} />
      <main className="events-main">
        {refreshError && <p role="status">{refreshError}</p>}
        <div className="bookings-title">
          <h1>Bookings</h1>
          <a className="event-secondary" href="/app/event-types">
            Open booking links
          </a>
        </div>
        <section className="event-card">
          <h2>Focus Guard · This week</h2>
          {loading || error ? (
            <p>
              {loading
                ? "Loading weekly counts…"
                : "Weekly counts unavailable. Refresh to retry."}
            </p>
          ) : (
            <>
              <p>
                {weekRows.length}{" "}
                {weekRows.length === 1 ? "meeting" : "meetings"} ·{" "}
                {weekRows.reduce((sum, b) => sum + b.duration, 0)} /{" "}
                {data?.schedule?.weekly_cap_minutes ?? "—"} minutes
              </p>
              <p>
                Saved bookings in {zone}. External busy intervals also protect
                availability when connected.
              </p>
              <div className="focus-week">
                {weekKeys.map((key, i) => {
                  const count = weekRows.filter(
                    (b) => localKey(new Date(b.start_at)) === key,
                  ).length;
                  const cap = data?.schedule?.host_daily_cap || 4;
                  return (
                    <div key={key}>
                      <div className="focus-track">
                        <span
                          style={{
                            height: `${Math.min(100, (count / cap) * 100)}%`,
                          }}
                          className={count >= cap ? "full" : ""}
                        />
                      </div>
                      <small>
                        {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][i]} ·{" "}
                        {count}/{cap}
                      </small>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </section>
        <div className="bookings-controls">
          <label>
            Booking month
            <input
              type="month"
              value={`${month.getFullYear()}-${String(month.getMonth() + 1).padStart(2, "0")}`}
              onChange={(e) => {
                if (e.target.value) {
                  const [y, m] = e.target.value.split("-").map(Number);
                  setMonth(new Date(y, m - 1, 1));
                }
              }}
            />
          </label>
          <div className="booking-filter">
            <label htmlFor="booking-filter">Show</label>
            <select
              id="booking-filter"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            >
              <option value="upcoming">Upcoming</option>
              <option value="past">Past</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </div>
          <button
            className="event-secondary"
            onClick={() => setRetry(retry + 1)}
          >
            Refresh
          </button>
        </div>
        {loading ? (
          <p role="status">Loading bookings…</p>
        ) : error ? (
          <p role="alert">{error}</p>
        ) : (
          <>
            <p>
              Times shown in {zone}.{" "}
              {data?.truncated &&
                "First 500 bookings shown; choose a narrower month."}
            </p>
            {rows.length === 0 ? (
              <section className="event-card">
                <h2>No {filter} bookings this month.</h2>
                <p>
                  Share a published event link to receive your first booking.
                </p>
              </section>
            ) : (
              <div className="booking-list">
                {rows.map((b) => (
                  <article className="event-card booking-row" key={b.id}>
                    <div>
                      <strong>{bookingTime(b.start_at, zone)}</strong>
                      <p>
                        {b.duration} minutes · {b.snapshot.title}
                      </p>
                    </div>
                    <div>
                      <strong>{b.invitee_name}</strong>
                      <p>{b.invitee_email}</p>
                      <small>{b.invitee_timezone}</small>
                    </div>
                    <div>
                      <span className="booking-status">
                        {b.status === "cancelled"
                          ? "Cancelled"
                          : "Confirmed · Free"}
                      </span>
                      <CalendarDelivery
                        status={b.calendar_status}
                        meetUrl={b.meet_url}
                        cancelled={b.status === "cancelled"}
                      />
                      {(b.calendar_status === "failed" ||
                        b.calendar_status === "retry") && (
                        <button
                          className="event-secondary"
                          onClick={async () => {
                            try {
                              await request(
                                `/api/me/bookings/${b.id}/calendar/retry`,
                                { method: "POST" },
                              );
                              setRetry(retry + 1);
                            } catch (e) {
                              setError((e as Error).message);
                            }
                          }}
                        >
                          Retry calendar delivery
                        </button>
                      )}
                      <EmailDelivery status={b.email_status} />
                      {b.host_email_status &&
                        b.host_email_status !== "not_enabled" && (
                          <p>
                            Host notification:{" "}
                            {b.host_email_status === "accepted"
                              ? "accepted by the email service"
                              : b.host_email_status}
                          </p>
                        )}
                    </div>
                    <BookingManagement
                      booking={b}
                      hostRequest={request}
                      onSaved={() => setRetry(retry + 1)}
                    />
                  </article>
                ))}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
