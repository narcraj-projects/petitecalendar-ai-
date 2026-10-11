import { useEffect, useId, useState } from "react";
import BookingForm from "./BookingForm";
import { notifyBookingChanged } from "../useLiveRefresh";
import "../assistant.css";

type Slot = { start: string; end: string; date: string };
type Result = {
  kind: string;
  message: string;
  action?: string;
  diff?: { field: string; before: unknown; after: unknown }[];
  proposal?: string;
  expires_at?: string;
  slots?: Slot[];
  timezone?: string;
  host_timezone?: string;
  duration?: number;
  booking_review?: {
    start: string;
    timezone: string;
    host_timezone: string;
    duration: number;
  };
};
const time = (value: string, zone: string) =>
  new Intl.DateTimeFormat("en-GB", {
    timeZone: zone,
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "shortOffset",
  }).format(new Date(value));
const labels: Record<string, string> = {
  durations: "Duration options (minutes)",
  default_duration: "Default duration (minutes)",
  notice_minutes: "Minimum notice (minutes)",
  horizon_days: "Booking horizon (days)",
  buffer_before: "Buffer before (minutes)",
  buffer_after: "Buffer after (minutes)",
  max_per_day: "Daily event limit",
  cancellation_hours: "Cancellation cutoff (hours)",
  reschedule_hours: "Reschedule cutoff (hours)",
  reschedule_requires_approval: "Host approval",
  allow_alternatives: "Alternative times",
  timezone: "Schedule timezone",
  weekly: "Working hours",
  focus: "Focus blocks",
  increment_minutes: "Slot interval (minutes)",
  host_daily_cap: "Host daily limit",
  weekly_cap_minutes: "Weekly meeting limit (minutes)",
  prefer_cluster: "Prefer nearby times",
  status: "Booking status",
};
function display(value: any): string {
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value))
    return value.length
      ? value
          .map((v) =>
            typeof v === "object"
              ? `${["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][v.weekday]} ${v.start}–${v.end}`
              : String(v),
          )
          .join(", ")
      : "None";
  return String(value);
}
export default function AssistantPanel({
  endpoint,
  timezone,
  duration,
  target,
  eventId,
  request,
  headers,
  onSaved,
  onSelect,
  bookingEndpoint,
}: {
  endpoint: string;
  timezone: string;
  duration: number;
  target?: "event" | "schedule";
  eventId?: string;
  request?: (url: string, options?: RequestInit) => Promise<any>;
  headers?: Record<string, string>;
  onSaved?: (body: any) => void;
  onSelect?: (start: string, timezone: string) => void;
  bookingEndpoint?: string;
}) {
  const id = useId();
  const [message, setMessage] = useState(""),
    [messages, setMessages] = useState<string[]>([]);
  const [result, setResult] = useState<Result>(),
    [error, setError] = useState("");
  const [busy, setBusy] = useState(false),
    [uncertain, setUncertain] = useState(false);
  const [slot, setSlot] = useState<Slot>(),
    [zoneConfirmed, setZoneConfirmed] = useState(false);
  const [zone, setZone] = useState(timezone);
  const [notice, setNotice] = useState("");
  const [expired, setExpired] = useState(false);
  useEffect(() => {
    setExpired(false);
    if (!result?.expires_at) return;
    const timer = setTimeout(
      () => {
        setExpired(true);
        setSlot(undefined);
      },
      Math.max(0, Date.parse(result.expires_at) - Date.now()),
    );
    return () => clearTimeout(timer);
  }, [result]);
  async function send(url: string, body: object) {
    const options = {
      method: "POST",
      headers: { "Content-Type": "application/json", ...headers },
      body: JSON.stringify(body),
    };
    if (request) return request(url, options);
    const r = await fetch(url, options),
      data = await r.json();
    if (!r.ok)
      throw Object.assign(
        new Error(data.error?.message || "The assistant is unavailable."),
        { status: r.status },
      );
    return data;
  }
  async function ask() {
    const next = [...messages, message.trim()].slice(-6);
    setBusy(true);
    setError("");
    setResult(undefined);
    setSlot(undefined);
    setNotice("");
    try {
      const data = await send(endpoint, {
        messages: next,
        timezone: zone,
        duration,
        target: target || "event",
        ...(eventId ? { event_id: eventId } : {}),
      });
      setResult(data);
      if (data.kind === "slots" && data.timezone) setZone(data.timezone);
      setMessages(next);
      setMessage("");
      setZoneConfirmed(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function confirm() {
    if (!result?.proposal) return;
    setBusy(true);
    setError("");
    try {
      const data = await send(endpoint + "/confirm", {
        proposal: result.proposal,
      });
      setUncertain(false);
      setResult(undefined);
      setMessages([]);
      setNotice(
        data.booking
          ? "Booking cancelled. Your time has been released."
          : "Settings saved. Available times will use the updated rules.",
      );
      onSaved?.(data);
      notifyBookingChanged();
    } catch (e) {
      const status = (e as Error & { status?: number }).status;
      setUncertain(!status || status >= 500);
      if (status && status < 500) setResult(undefined);
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const zones = Array.from(
    new Set([zone, "UTC", ...Intl.supportedValuesOf("timeZone")]),
  ).sort();
  return (
    <details className="assistant-panel">
      <summary>
        {target
          ? "Draft settings with the assistant"
          : "Find a time with the assistant"}
      </summary>
      <div className="assistant-content">
        <p className="assistant-disclosure">
          Your request is sent to OpenAI. Keep names, emails and calendar
          details out of it. Suggestions need your review.
        </p>
        <label htmlFor={id + "zone"}>Assistant time zone</label>
        <select
          id={id + "zone"}
          value={zone}
          disabled={busy || uncertain}
          onChange={(e) => {
            setZone(e.target.value);
            setResult(undefined);
            setSlot(undefined);
            setMessages([]);
          }}
        >
          {zones.map((z) => (
            <option key={z}>{z}</option>
          ))}
        </select>
        {result?.kind === "clarification" && (
          <p role="status">{result.message}</p>
        )}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void ask();
          }}
        >
          <label htmlFor={id + "message"}>
            {target
              ? "Describe the settings change"
              : "Describe when you would like to meet"}
          </label>
          <textarea
            id={id + "message"}
            maxLength={1000}
            required
            value={message}
            disabled={busy || uncertain}
            placeholder={
              target
                ? "Make this 45 minutes with a 15 minute buffer"
                : "Next Tuesday afternoon in London"
            }
            onChange={(e) => {
              setMessage(e.target.value);
              setResult(undefined);
              setSlot(undefined);
            }}
          />
          <button
            className="event-secondary"
            disabled={busy || uncertain || !message.trim()}
          >
            {busy ? "Working…" : "Ask assistant"}
          </button>
        </form>
        {error && <p role="alert">{error} You can use the manual controls.</p>}
        {notice && <p role="status">{notice}</p>}
        {result && result.kind !== "clarification" && (
          <div className="assistant-result" aria-live="polite">
            <p>{result.message}</p>
            {result.kind === "proposal" && (
              <>
                {result.booking_review && (
                  <div>
                    <p>
                      Your time:{" "}
                      {time(
                        result.booking_review.start,
                        result.booking_review.timezone,
                      )}
                    </p>
                    <p>
                      Host:{" "}
                      {time(
                        result.booking_review.start,
                        result.booking_review.host_timezone,
                      )}
                    </p>
                    <p>{result.booking_review.duration} minutes</p>
                  </div>
                )}
                <dl className="assistant-diff">
                  {result.diff?.map((d) => (
                    <div key={d.field}>
                      <dt>{labels[d.field] || d.field}</dt>
                      <dd>
                        <span>Current: {display(d.before)}</span>
                        <strong>Proposed: {display(d.after)}</strong>
                      </dd>
                    </div>
                  ))}
                </dl>
                <p>
                  Review expires in 15 minutes.{" "}
                  {result.action === "schedule" &&
                    "This affects every event type using your schedule."}
                </p>
                {uncertain && (
                  <p>
                    The outcome is not verified. Retry this exact proposal
                    before another change.
                  </p>
                )}
                <button
                  className="event-primary"
                  disabled={busy || (expired && !uncertain)}
                  onClick={() => void confirm()}
                >
                  {uncertain
                    ? "Retry same proposal"
                    : result.action === "cancel"
                      ? "Confirm cancellation"
                      : "Apply reviewed changes"}
                </button>
                {!uncertain && (
                  <button
                    className="event-secondary"
                    disabled={busy}
                    onClick={() => setResult(undefined)}
                  >
                    Discard proposal
                  </button>
                )}
              </>
            )}
            {result.kind === "slots" && (
              <>
                <p>
                  {result.duration} minutes · Your zone: {result.timezone}
                </p>
                <div className="assistant-slots">
                  {result.slots?.map((s) => (
                    <button
                      className="event-secondary"
                      disabled={expired || busy}
                      key={s.start}
                      onClick={() => {
                        setSlot(s);
                        setZoneConfirmed(false);
                      }}
                    >
                      <strong>{time(s.start, result.timezone!)}</strong>
                      <span>Host: {time(s.start, result.host_timezone!)}</span>
                    </button>
                  ))}
                </div>
                {slot && (
                  <div className="assistant-time-review">
                    {!zoneConfirmed ? (
                      <>
                        <h3>Check your current time zone.</h3>
                        <p>
                          Are you currently using {result.timezone}? Your travel
                          location may differ from the device setting.
                        </p>
                        <button
                          className="event-primary"
                          disabled={expired}
                          onClick={() => setZoneConfirmed(true)}
                        >
                          Yes, confirm zone & review
                        </button>
                        <button
                          className="event-secondary"
                          onClick={() => {
                            setSlot(undefined);
                            document.getElementById(id + "zone")?.focus();
                          }}
                        >
                          Change my time zone
                        </button>
                      </>
                    ) : (
                      <>
                        <h3>Your selected time</h3>
                        <p>You: {time(slot.start, result.timezone!)}</p>
                        <p>Host: {time(slot.start, result.host_timezone!)}</p>
                        <p>{result.duration} minutes</p>
                        {onSelect ? (
                          <button
                            className="event-primary"
                            disabled={expired}
                            onClick={() => {
                              onSelect(slot.start, result.timezone!);
                              setSlot(undefined);
                              setResult(undefined);
                            }}
                          >
                            Use this time
                          </button>
                        ) : (
                          bookingEndpoint &&
                          !expired && (
                            <BookingForm
                              key={slot.start + result.timezone}
                              endpoint={bookingEndpoint}
                              start={slot.start}
                              duration={result.duration!}
                              timezone={result.timezone!}
                              onConflict={() => {
                                setSlot(undefined);
                                setResult(undefined);
                                setError(
                                  "That time is no longer available. Ask again or use the calendar.",
                                );
                              }}
                            />
                          )
                        )}
                      </>
                    )}
                  </div>
                )}
              </>
            )}
            {expired && (
              <p role="status">This proposal expired. Ask for fresh options.</p>
            )}
          </div>
        )}
      </div>
    </details>
  );
}
