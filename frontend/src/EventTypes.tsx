import { useEffect, useRef, useState } from "react";
import {
  CalendarDays,
  Plus,
  ExternalLink,
  Copy,
  ArrowRight,
} from "lucide-react";
import EventEditor, {
  blankEvent,
  type EventType,
} from "./components/EventEditor";
import "./events.css";
import HostNavigation from "./components/HostNavigation";
import AssistantPanel from "./components/AssistantPanel";

export default function EventTypes({
  profile,
  request,
  signOut,
}: {
  profile: { display_name: string; username: string; timezone: string };
  request: (url: string, options?: RequestInit) => Promise<any>;
  signOut: () => void;
}) {
  const [events, setEvents] = useState<EventType[]>([]);
  const [loading, setLoading] = useState(true);
  const [editor, setEditor] = useState<EventType | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [assistantTarget, setAssistantTarget] = useState("");
  const requestRef = useRef(request);
  requestRef.current = request;
  async function load() {
    setError("");
    setLoading(true);
    try {
      const { events: list } = await requestRef.current("/api/me/event-types");
      setEvents(list);
      const segment = window.location.pathname.split("/")[3];
      if (segment === "new") setEditor({ ...blankEvent });
      else if (segment) {
        const found = list.find((e: EventType) => e.id === segment);
        if (!found) throw new Error("This event type is not available.");
        setEditor(found);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void load();
  }, []);
  function open(event: EventType) {
    setEditor({ ...event });
    setNotice("");
    window.history.pushState({}, "", `/app/event-types/${event.id || "new"}`);
  }
  function back() {
    setEditor(null);
    setError("");
    window.history.pushState({}, "", "/app/event-types");
  }
  useEffect(() => {
    const handle = () => {
      setEditor(null);
      void load();
    };
    window.addEventListener("popstate", handle);
    return () => window.removeEventListener("popstate", handle);
  }, []);
  async function save(event: EventType) {
    const { id, ...body } = event;
    if (!id) {
      delete body.revision;
      delete (body as Partial<EventType>).published;
    }
    const result = await request("/api/me/event-types" + (id ? `/${id}` : ""), {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(body),
    });
    setEvents((previous) => [
      result.event,
      ...previous.filter((e) => e.id !== result.event.id),
    ]);
    setEditor(result.event);
    window.history.replaceState({}, "", `/app/event-types/${result.event.id}`);
    setNotice(
      result.event.published ? "Event saved and published." : "Draft saved.",
    );
  }
  async function copy(event: EventType) {
    try {
      await navigator.clipboard.writeText(
        `${window.location.origin}/${profile.username}/${event.slug}`,
      );
      setNotice("Public link copied.");
    } catch {
      setError(
        "Could not copy the link. Open the public page and copy its address.",
      );
    }
  }
  return (
    <div className="events-shell">
      <HostNavigation profile={profile} current="events" signOut={signOut} />
      <main className="events-main">
        {loading ? (
          <p role="status">Loading event types…</p>
        ) : editor ? (
          <EventEditor
            key={`${editor.id || "new"}-${editor.revision || 0}`}
            initial={editor}
            username={profile.username}
            onSave={save}
            onBack={back}
          />
        ) : (
          <>
            <div className="event-title-row">
              <div>
                <span className="event-eyebrow">
                  MAKE ROOM FOR GOOD CONVERSATIONS
                </span>
                <h1>Event types</h1>
                <p>Create the conversations people can schedule with you.</p>
              </div>
              <button
                className="event-primary"
                onClick={() => open({ ...blankEvent })}
              >
                <Plus size={18} />
                New event type
              </button>
            </div>
            {events.length > 0 && (
              <>
                <label className="assistant-target">
                  Assistant settings target
                  <select
                    value={assistantTarget || events[0].id}
                    onChange={(e) => setAssistantTarget(e.target.value)}
                  >
                    {events.map((e) => (
                      <option key={e.id} value={e.id}>
                        {e.title}
                      </option>
                    ))}
                    <option value="schedule">
                      Shared availability & Focus Guard
                    </option>
                  </select>
                </label>
                <AssistantPanel
                  key={
                    (assistantTarget || events[0].id) +
                    events.map((e) => e.revision).join("-")
                  }
                  endpoint="/api/me/assistant"
                  request={request}
                  target={assistantTarget === "schedule" ? "schedule" : "event"}
                  eventId={
                    assistantTarget === "schedule"
                      ? undefined
                      : assistantTarget || events[0].id
                  }
                  timezone={profile.timezone}
                  duration={30}
                  onSaved={() => {
                    setNotice("Assistant changes saved.");
                    void load();
                  }}
                />
              </>
            )}
            {events.length === 0 && !error ? (
              <div className="event-empty event-card">
                <CalendarDays size={36} />
                <h2>Your first conversation starts here.</h2>
                <p>
                  Create a draft, set its durations and policies, then publish
                  your event page.
                </p>
                <button
                  className="event-primary"
                  onClick={() => open({ ...blankEvent })}
                >
                  Create your first event <ArrowRight size={18} />
                </button>
              </div>
            ) : (
              <div className="event-list">
                {events.map((event) => (
                  <article className="event-card" key={event.id}>
                    <span
                      className={`event-status ${event.published ? "is-published" : ""}`}
                    >
                      {event.published ? "Published" : "Draft"}
                    </span>
                    <h2>{event.title}</h2>
                    <p>
                      {event.durations.join(" / ")} min · {event.location}
                    </p>
                    <p className="event-link">
                      /{profile.username}/{event.slug}
                    </p>
                    <div className="event-card-actions">
                      <button
                        className="event-secondary"
                        onClick={() => open(event)}
                      >
                        Edit event
                      </button>
                      {event.published && (
                        <>
                          <a
                            className="event-secondary"
                            href={`/${profile.username}/${event.slug}`}
                            target="_blank"
                            rel="noreferrer"
                          >
                            <ExternalLink size={16} />
                            View page
                          </a>
                          <button
                            className="event-secondary"
                            aria-label={`Copy link for ${event.title}`}
                            onClick={() => void copy(event)}
                          >
                            <Copy size={16} />
                          </button>
                        </>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            )}
          </>
        )}
        {error && (
          <div className="event-error" role="alert">
            {error}
            <button className="event-secondary" onClick={() => void load()}>
              Reload event types
            </button>
          </div>
        )}
        {notice && (
          <p className="event-notice" role="status">
            {notice}
          </p>
        )}
      </main>
    </div>
  );
}
