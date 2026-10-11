import { useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Globe, X } from "lucide-react";
import "../availability.css";
import BookingForm from "./BookingForm";
import "../bookings.css";
import { useLiveRefresh } from "../useLiveRefresh";
type Slot = { start: string; end: string; date: string; recommended?: boolean };
const dateKey = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const zoneTime = (value: string, zone: string) =>
  new Intl.DateTimeFormat("en-GB", {
    timeZone: zone,
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "shortOffset",
  }).format(new Date(value));
const reviewTime = (value: string, zone: string) =>
  new Intl.DateTimeFormat("en-GB", {
    timeZone: zone,
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "shortOffset",
  }).format(new Date(value));
const reasons: Record<string, string> = {
  closed_days: "Closed days or date overrides",
  minimum_notice: "Minimum notice",
  booking_horizon: "Booking horizon",
  duration_and_buffers: "Duration and buffers",
  focus_blocks: "Protected focus blocks",
  meeting_limits: "Daily or weekly meeting limits",
  occupied_times: "Existing meetings",
  availability_paused: "The host has paused availability",
  availability_not_configured: "The host has not set availability",
};
export default function AvailabilityPicker({
  duration,
  hostZone,
  endpoint,
  headers,
  onSelect,
  request,
}: {
  duration: number;
  hostZone: string;
  endpoint: string;
  headers?: Record<string, string>;
  onSelect?: (start: string, timezone: string) => void;
  request?: (url: string, options?: RequestInit) => Promise<any>;
}) {
  const refresh = useLiveRefresh();
  const requestContext = useRef("");
  const selection = useRef<Slot | undefined>(undefined);
  const device = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  const [zone, setZone] = useState(device),
    [source, setSource] = useState<"device" | "chosen">("device");
  const [month, setMonth] = useState(
    new Date(new Date().getFullYear(), new Date().getMonth(), 1),
  );
  const [slots, setSlots] = useState<Slot[]>([]),
    [day, setDay] = useState(""),
    [selected, setSelected] = useState<Slot>();
  const [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [explanations, setExplanations] = useState<string[]>([]),
    [retry, setRetry] = useState(0),
    [notice, setNotice] = useState("");
  const [review, setReview] = useState(false),
    [confirmed, setConfirmed] = useState(false);
  const [calendarStatus, setCalendarStatus] = useState("not_connected");
  selection.current = selected;
  const dialog = useRef<HTMLDialogElement>(null),
    zoneInput = useRef<HTMLSelectElement>(null);
  useEffect(() => {
    const controller = new AbortController();
    const context = `${endpoint}:${month.toISOString()}:${zone}:${duration}`;
    const background = requestContext.current === context;
    requestContext.current = context;
    if (!background) {
      setLoading(true);
      setError("");
      setSlots([]);
      setSelected(undefined);
      setReview(false);
    }
    const query = new URLSearchParams({
      start_date: dateKey(month),
      end_date: dateKey(new Date(month.getFullYear(), month.getMonth() + 1, 0)),
      duration: String(duration),
      timezone: zone,
    });
    (request
      ? request(`${endpoint}/slots?${query}`, {
          signal: controller.signal,
        }).then((body) => ({ ok: true, json: async () => body }))
      : fetch(`${endpoint}/slots?${query}`, {
          signal: controller.signal,
          headers,
        })
    )
      .then(async (r) => {
        const body = await r.json();
        if (!r.ok)
          throw new Error(
            body.error?.message || "Available times could not be loaded.",
          );
        setSlots(body.slots);
        setError("");
        const chosen = selection.current;
        if (
          background &&
          chosen &&
          !body.slots.some(
            (s: Slot) => s.start === chosen.start && s.end === chosen.end,
          )
        ) {
          setSelected(undefined);
          setReview(false);
          setNotice(
            "Your selected time is no longer available. Choose another time.",
          );
        }
        setCalendarStatus(body.calendar_status || "not_connected");
        setExplanations(body.explanations || []);
        setDay((previous) =>
          body.slots.some((s: Slot) => s.date === previous)
            ? previous
            : body.slots[0]?.date || "",
        );
        setLoading(false);
      })
      .catch((e) => {
        if (e.name !== "AbortError") {
          if (background && slots.length)
            setNotice(
              "Availability could not refresh. Retrying automatically; your time will be checked before confirmation.",
            );
          else setError(e.message);
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [month, zone, duration, retry, endpoint, refresh]);
  useEffect(() => {
    if (review) dialog.current?.showModal();
    else dialog.current?.close();
  }, [review]);
  const count = new Date(
    month.getFullYear(),
    month.getMonth() + 1,
    0,
  ).getDate();
  const padding = (month.getDay() + 6) % 7;
  const available = new Set(slots.map((s) => s.date));
  const zones = Array.from(
    new Set([zone, "UTC", ...Intl.supportedValuesOf("timeZone")]),
  ).sort();
  function openReview() {
    const current = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
    if (source === "device" && current !== zone) {
      setZone(current);
      setSelected(undefined);
      setNotice(
        "Your device timezone changed. Choose a time again in the updated zone.",
      );
      return;
    }
    setConfirmed(false);
    setReview(true);
  }
  return (
    <>
      <section className="event-card availability-picker">
        <h2>Choose a time</h2>
        <p>
          Available times from the host’s saved schedule and existing bookings.
          {calendarStatus === "connected"
            ? "Selected Google calendars also protect busy times."
            : "External calendars are not connected."}
        </p>
        <label htmlFor="invitee-zone" className="picker-zone-label">
          <Globe size={15} />
          Your current time zone
        </label>
        <select
          ref={zoneInput}
          id="invitee-zone"
          value={zone}
          onChange={(e) => {
            setSource("chosen");
            setZone(e.target.value);
            setNotice("");
            setSelected(undefined);
            setReview(false);
          }}
        >
          {zones.map((z) => (
            <option key={z}>{z}</option>
          ))}
        </select>
        <p>
          {source === "device"
            ? "Suggested by your device."
            : "Selected by you."}{" "}
          Confirm your current or travel zone before reviewing a time.
        </p>
        {notice && <p role="status">{notice}</p>}
        <div className="picker-month">
          <button
            className="event-secondary"
            aria-label="Previous month"
            onClick={() =>
              setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))
            }
          >
            <ChevronLeft size={18} />
          </button>
          <strong>
            {month.toLocaleDateString("en-GB", {
              month: "long",
              year: "numeric",
            })}
          </strong>
          <button
            className="event-secondary"
            aria-label="Next month"
            onClick={() =>
              setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))
            }
          >
            <ChevronRight size={18} />
          </button>
        </div>
        {loading ? (
          <p role="status" className="picker-loading">
            Finding available times…
          </p>
        ) : error ? (
          <div role="alert" className="event-error">
            {error}
            <button
              className="event-secondary"
              onClick={() => setRetry(retry + 1)}
            >
              Retry times
            </button>
          </div>
        ) : (
          <>
            <div className="picker-calendar" aria-label="Available dates">
              {["M", "T", "W", "T", "F", "S", "S"].map((label, index) => (
                <span className="picker-weekday" key={index}>
                  {label}
                </span>
              ))}
              {Array.from({ length: padding }, (_, i) => (
                <span key={`empty-${i}`} />
              ))}
              {Array.from({ length: count }, (_, i) => {
                const key = dateKey(
                  new Date(month.getFullYear(), month.getMonth(), i + 1),
                );
                return (
                  <button
                    key={key}
                    className={`picker-day ${available.has(key) ? "available" : ""}`}
                    disabled={!available.has(key)}
                    aria-pressed={day === key}
                    aria-label={key}
                    onClick={() => {
                      setDay(key);
                      setSelected(undefined);
                    }}
                  >
                    {i + 1}
                  </button>
                );
              })}
            </div>
            {slots.length === 0 ? (
              <p role="status">
                No available times this month. Try another month or duration.
              </p>
            ) : (
              <>
                <p>
                  {day
                    ? new Date(day + "T12:00:00").toLocaleDateString("en-GB", {
                        weekday: "long",
                        day: "numeric",
                        month: "long",
                      })
                    : ""}
                </p>
                <div className="picker-slots">
                  {slots
                    .filter((s) => s.date === day)
                    .map((s) => (
                      <button
                        key={s.start}
                        className="picker-slot"
                        data-start={s.start}
                        aria-pressed={selected?.start === s.start}
                        onClick={() => setSelected(s)}
                      >
                        <strong>{zoneTime(s.start, zone)}</strong>
                        <small>Host: {zoneTime(s.start, hostZone)}</small>
                        {s.recommended && (
                          <small className="picker-recommended">
                            Recommended
                          </small>
                        )}
                      </button>
                    ))}
                </div>
              </>
            )}
            {selected && (
              <button
                className="event-primary picker-review"
                onClick={openReview}
              >
                Review selected time
              </button>
            )}
            {explanations.length > 0 && (
              <div className="picker-explanations">
                Rules filtering times:{" "}
                {explanations.map((r) => reasons[r] || r).join(" · ")}
              </div>
            )}
          </>
        )}
      </section>
      <dialog
        ref={dialog}
        className="slot-review-dialog"
        onCancel={() => setReview(false)}
        onClose={() => setReview(false)}
      >
        <button
          className="slot-review-close"
          aria-label="Close review"
          onClick={() => setReview(false)}
        >
          <X size={20} />
        </button>
        {!confirmed ? (
          <>
            <h2>Check your current time zone.</h2>
            <p>
              Are you currently using <strong>{zone}</strong>? Your device
              setting may differ from your travel location.
            </p>
            <button
              className="event-primary"
              onClick={() => setConfirmed(true)}
            >
              Yes, confirm zone & review
            </button>
            <button
              className="event-secondary"
              onClick={() => {
                setReview(false);
                setTimeout(() => zoneInput.current?.focus(), 0);
              }}
            >
              Change my time zone
            </button>
          </>
        ) : (
          <>
            <h2>Your selected time</h2>
            <dl>
              <dt>YOU · {zone}</dt>
              <dd>{selected && reviewTime(selected.start, zone)}</dd>
              <dt>HOST · {hostZone}</dt>
              <dd>{selected && reviewTime(selected.start, hostZone)}</dd>
              <dt>Duration</dt>
              <dd>{duration} minutes</dd>
            </dl>
            {selected && onSelect ? (
              <button
                className="event-primary"
                onClick={() => {
                  onSelect(selected.start, zone);
                  setReview(false);
                }}
              >
                Use this time
              </button>
            ) : (
              selected && (
                <BookingForm
                  key={`${selected.start}-${duration}-${zone}`}
                  endpoint={endpoint}
                  start={selected.start}
                  duration={duration}
                  timezone={zone}
                  onConflict={() => {
                    setReview(false);
                    setSelected(undefined);
                    setNotice(
                      "That time is no longer available. Choose another time.",
                    );
                    setRetry(retry + 1);
                  }}
                />
              )
            )}
          </>
        )}
      </dialog>
    </>
  );
}
