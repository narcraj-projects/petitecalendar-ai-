import { useEffect, useState } from "react";
import { CalendarDays, Clock3, Globe, ShieldCheck } from "lucide-react";
import DurationToggle from "./components/DurationToggle";
import AvailabilityPicker from "./components/AvailabilityPicker";
import AssistantPanel from "./components/AssistantPanel";
import { BookingContactProvider } from "./components/BookingContact";
import "./events.css";
type PublicEvent = {
  title: string;
  description: string;
  host: { name: string; timezone: string };
  durations: number[];
  default_duration: number;
  location: string;
  notice_minutes: number;
  buffer_before: number;
  buffer_after: number;
  cancellation_hours: number;
  reschedule_hours: number;
  reschedule_requires_approval: boolean;
  availability_ready?: boolean;
  availability_status?: string;
  schedule_timezone?: string;
};
export default function PublishedEvent() {
  return (
    <BookingContactProvider>
      <PublishedEventContent />
    </BookingContactProvider>
  );
}
function PublishedEventContent() {
  const [event, setEvent] = useState<PublicEvent>();
  const [duration, setDuration] = useState(0);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/public/events" + window.location.pathname, {
      signal: controller.signal,
    })
      .then(async (r) => {
        const body = await r.json();
        if (!r.ok)
          throw new Error(
            body.error?.message || "This event is not available.",
          );
        setEvent(body);
        setDuration(body.default_duration);
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, []);
  return (
    <div className="published-shell">
      <header>
        <a className="event-brand" href="/login">
          <CalendarDays size={24} />
          PetCalendar AI
        </a>
        <span>Event details</span>
      </header>
      <main>
        {error ? (
          <section className="event-card">
            <h1>This event is not available.</h1>
            <p role="alert">{error}</p>
          </section>
        ) : !event ? (
          <p role="status">Loading event details…</p>
        ) : (
          <div className="published-grid">
            <section className="event-card">
              <span className="event-eyebrow">
                A CONVERSATION WITH {event.host.name.toUpperCase()}
              </span>
              <h1>{event.title}</h1>
              <p className="published-description">{event.description}</p>
              <DurationToggle
                options={event.durations}
                value={duration}
                onChange={setDuration}
              />
              <dl className="event-public-facts">
                <div>
                  <dt>
                    <Clock3 size={18} />
                    Duration
                  </dt>
                  <dd>{duration} minutes</dd>
                </div>
                <div>
                  <dt>Location</dt>
                  <dd>{event.location}</dd>
                </div>
                <div>
                  <dt>
                    <Globe size={18} />
                    Host timezone
                  </dt>
                  <dd>{event.schedule_timezone || event.host.timezone}</dd>
                </div>
                <div>
                  <dt>Minimum notice</dt>
                  <dd>{event.notice_minutes} minutes</dd>
                </div>
              </dl>
              <div className="event-guard">
                <ShieldCheck size={20} />
                <p>
                  Cancel until {event.cancellation_hours} hours before.
                  Reschedule until {event.reschedule_hours} hours before
                  {event.reschedule_requires_approval
                    ? ", with host approval"
                    : ""}
                  .
                </p>
              </div>
              {event.availability_ready && (
                <AssistantPanel
                  key={duration}
                  endpoint={
                    "/api/public/events" +
                    window.location.pathname +
                    "/assistant"
                  }
                  bookingEndpoint={
                    "/api/public/events" + window.location.pathname
                  }
                  duration={duration}
                  timezone={
                    Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"
                  }
                />
              )}
            </section>
            {event.availability_ready ? (
              <AvailabilityPicker
                duration={duration}
                hostZone={event.schedule_timezone || event.host.timezone}
                endpoint={"/api/public/events" + window.location.pathname}
              />
            ) : (
              <section className="event-card">
                <CalendarDays size={32} />
                <h2>
                  {event.availability_status === "paused"
                    ? "Scheduling is paused."
                    : "Scheduling will open soon."}
                </h2>
                <p>
                  {event.availability_status === "paused"
                    ? "The host has paused available times for this event."
                    : `${event.host.name} has published this event’s details. Available times are not configured yet.`}
                </p>
                <p>Check back after the host sets their availability.</p>
              </section>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
