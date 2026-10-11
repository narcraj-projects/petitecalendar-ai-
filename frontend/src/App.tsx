import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  CalendarDays,
  Check,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Globe2,
  LockKeyhole,
  ShieldCheck,
  Video,
  X,
} from "lucide-react";
import DurationToggle from "./components/DurationToggle";

type Slot = { start: string; end: string; date: string };
type Event = {
  title: string;
  description: string;
  host: { name: string; role: string; timezone: string };
  durations: number[];
  default_duration: number;
  now: string;
  horizon_days: number;
  notice_hours: number;
};
const ENDPOINT = "/api/public/events/ananya/career-strategy";
const ZONES = [
  "Asia/Kolkata",
  "Europe/London",
  "America/New_York",
  "Asia/Singapore",
  "Asia/Kathmandu",
  "Asia/Dubai",
  "Australia/Sydney",
  "UTC",
  ...Intl.supportedValuesOf("timeZone"),
];
const dateKey = (date: Date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
const zoneDate = (date: string, zone: string) =>
  new Intl.DateTimeFormat("en-CA", {
    timeZone: zone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(date));
const timeLabel = (date: string, zone: string) =>
  new Intl.DateTimeFormat("en-GB", {
    timeZone: zone,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(date));
const prettyDate = (key: string) =>
  new Date(`${key}T12:00:00`).toLocaleDateString("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
const zoneName = (zone: string) =>
  zone === "UTC" ? "UTC" : zone.split("/").at(-1)!.replaceAll("_", " ");
async function fetchJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  const body = await response.json();
  if (!response.ok)
    throw new Error(body.error?.message ?? "We could not load the schedule.");
  return body;
}

export default function App() {
  const browserZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const [zone, setZone] = useState(browserZone || "Asia/Kolkata");
  const [event, setEvent] = useState<Event | null>(null);
  const [month, setMonth] = useState(
    new Date(new Date().getFullYear(), new Date().getMonth(), 1),
  );
  const [duration, setDuration] = useState(45);
  const [slots, setSlots] = useState<Slot[]>([]);
  const [day, setDay] = useState("");
  const [selected, setSelected] = useState<Slot | null>(null);
  const [review, setReview] = useState(false);
  const [reviewStage, setReviewStage] = useState<"timezone" | "summary">(
    "timezone",
  );
  const [zoneSource, setZoneSource] = useState<"device" | "chosen">("device");
  const [zoneNotice, setZoneNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [mobileMonth, setMobileMonth] = useState(false);
  const [dayPage, setDayPage] = useState(0);
  const reviewTrigger = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchJson<Event>(ENDPOINT, controller.signal)
      .then((data) => {
        setEvent(data);
        const today = zoneDate(data.now, browserZone || "Asia/Kolkata");
        const local = new Date(`${today}T12:00:00`);
        setMonth(new Date(local.getFullYear(), local.getMonth(), 1));
      })
      .catch((err) => {
        if (err.name !== "AbortError") {
          setError(err.message);
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [retry]);

  useEffect(() => {
    if (!event) return;
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setSelected(null);
    setReview(false);
    const last = new Date(month.getFullYear(), month.getMonth() + 1, 0);
    const query = new URLSearchParams({
      start_date: dateKey(month),
      end_date: dateKey(last),
      duration: String(duration),
      timezone: zone,
    });
    fetchJson<{ slots: Slot[] }>(
      `${ENDPOINT}/slots?${query}`,
      controller.signal,
    )
      .then((data) => {
        setSlots(data.slots);
        setDay((previous) =>
          data.slots.some((slot) => slot.date === previous)
            ? previous
            : (data.slots[0]?.date ?? ""),
        );
        setLoading(false);
      })
      .catch((err) => {
        if (err.name !== "AbortError") {
          setError(err.message);
          setSlots([]);
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [event, month, duration, zone, retry]);

  useEffect(() => {
    if (!review) return;
    const background = document.querySelectorAll<HTMLElement>(
      "header, main, footer",
    );
    background.forEach((element) => {
      element.inert = true;
    });
    const close = (e: KeyboardEvent) => {
      if (e.key === "Escape") setReview(false);
      if (e.key === "Tab") {
        const buttons = document.querySelectorAll<HTMLButtonElement>(
          ".review-card button",
        );
        const first = buttons[0];
        const last = buttons[buttons.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        }
        if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener("keydown", close);
    return () => {
      window.removeEventListener("keydown", close);
      background.forEach((element) => {
        element.inert = false;
      });
      reviewTrigger.current?.focus();
    };
  }, [review]);

  const availableDays = useMemo(
    () => [...new Set(slots.map((slot) => slot.date))],
    [slots],
  );
  useEffect(() => {
    setDayPage(Math.max(0, Math.floor(availableDays.indexOf(day) / 5)));
  }, [day, availableDays]);
  const daySlots = slots.filter((slot) => slot.date === day);
  const morning = daySlots.filter(
    (slot) => Number(timeLabel(slot.start, zone).slice(0, 2)) < 12,
  );
  const afternoon = daySlots.filter(
    (slot) => Number(timeLabel(slot.start, zone).slice(0, 2)) >= 12,
  );
  const zones = [...new Set([zone, ...ZONES])];
  const firstWeekday = (month.getDay() + 6) % 7;
  const daysInMonth = new Date(
    month.getFullYear(),
    month.getMonth() + 1,
    0,
  ).getDate();
  const today = event
    ? new Date(`${zoneDate(event.now, zone)}T12:00:00`)
    : new Date();
  const firstMonth = new Date(today.getFullYear(), today.getMonth(), 1);
  const horizon = new Date(today);
  horizon.setDate(horizon.getDate() + (event?.horizon_days ?? 60));
  const lastMonth = new Date(horizon.getFullYear(), horizon.getMonth(), 1);
  const chooseDay = (key: string) => {
    setDay(key);
    setSelected(null);
    setMobileMonth(false);
  };
  const changeMonth = (offset: number) =>
    setMonth(new Date(month.getFullYear(), month.getMonth() + offset, 1));

  function renderSlots(group: Slot[], label: string) {
    if (!group.length) return null;
    return (
      <div className="slot-group">
        <h3>{label}</h3>
        {group.map((slot) => (
          <div className="slot-row" key={slot.start}>
            <button
              className={`slot ${selected?.start === slot.start ? "selected" : ""}`}
              onClick={() => setSelected(slot)}
              aria-pressed={selected?.start === slot.start}
            >
              <span>{timeLabel(slot.start, zone)}</span>
              <span className="host-time">
                {timeLabel(slot.start, event?.host.timezone ?? "Asia/Kolkata")}{" "}
                IST
              </span>
            </button>
            {selected?.start === slot.start && (
              <button
                className="next-button"
                onClick={(e) => {
                  reviewTrigger.current = e.currentTarget;
                  const currentDeviceZone =
                    Intl.DateTimeFormat().resolvedOptions().timeZone;
                  if (
                    zoneSource === "device" &&
                    currentDeviceZone &&
                    currentDeviceZone !== zone
                  ) {
                    setZone(currentDeviceZone);
                    setZoneNotice(
                      "Your device time zone changed. Choose a time in your current zone.",
                    );
                    return;
                  }
                  setReviewStage("timezone");
                  setReview(true);
                }}
              >
                Review <ArrowRight size={16} />
              </button>
            )}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="shell">
      <header className="site-header">
        <a
          className="brand"
          href="/ananya/career-strategy"
          aria-label="PetCalendar AI home"
        >
          <span className="brand-icon">
            <CalendarDays size={19} />
          </span>
          Pet<span>Calendar AI</span>
          <span className="brand-dot">.</span>
        </a>
        <span className="demo-pill">
          <span /> Demo schedule
        </span>
      </header>
      <main>
        <div className="intro">
          <div>
            <p className="eyebrow">GOOD CONVERSATIONS START HERE</p>
            <h1>A little time. A clear next step.</h1>
            <p className="intro-copy">
              Find a moment that works for you. Leave with a plan that moves you
              forward.
            </p>
          </div>
          <div className="intro-note">
            <ShieldCheck size={19} />
            <span>
              Space for a conversation.
              <br />
              <strong>Room for focused work.</strong>
            </span>
          </div>
        </div>
        <section
          className="booking-panel"
          aria-label="Book a career strategy call"
        >
          <aside className="host-panel">
            <div className="host-identity">
              <div className="avatar">AR</div>
              <div>
                <strong>{event?.host.name ?? "Ananya Rao"}</strong>
                <p>{event?.host.role ?? "Product & career coach"}</p>
              </div>
            </div>
            <div className="host-location">
              <Globe2 size={14} /> Based in India · IST
            </div>
            <div className="host-content">
              <p className="eyebrow">A CONVERSATION WITH PURPOSE</p>
              <h2>{event?.title ?? "Career strategy call"}</h2>
              <p className="description">
                {event?.description ??
                  "Bring your CV and the roles you're weighing. We'll leave with a 90-day plan."}
              </p>
              <DurationToggle
                options={event?.durations ?? [30, 45, 60]}
                value={duration}
                onChange={setDuration}
              />
              <dl className="event-facts">
                <div>
                  <dt>
                    <Clock3 size={17} /> Duration
                  </dt>
                  <dd>{duration} minutes</dd>
                </div>
                <div>
                  <dt>
                    <Video size={17} /> Location
                  </dt>
                  <dd>Online conversation</dd>
                </div>
                <div>
                  <dt>
                    <CalendarDays size={17} /> Notice
                  </dt>
                  <dd>{event?.notice_hours ?? 12} hours ahead</dd>
                </div>
              </dl>
            </div>
            <div className="focus-note">
              <ShieldCheck size={18} />
              <div>
                <strong>A little breathing room</strong>
                <p>10 minutes before, 15 after. Focus time stays protected.</p>
              </div>
            </div>
            <p className="mobile-policy-line">
              12 hours' notice · 10 min before, 15 min after
            </p>
            <p className="demo-disclosure">
              This preview uses a demo schedule. Choose a time to review it; no
              booking will be created.
            </p>
          </aside>
          <div className="scheduling-panel">
            <div className="schedule-heading">
              <div>
                <p className="eyebrow">MAKE SOME TIME</p>
                <h2>When works for you?</h2>
              </div>
              <span className="step-label">
                01 <span>/</span> SELECT A TIME
              </span>
            </div>
            <div className="schedule-grid">
              <div className="calendar-column">
                <div className="month-heading">
                  <h3>
                    {month.toLocaleDateString("en-GB", {
                      month: "long",
                      year: "numeric",
                    })}
                  </h3>
                  <div className="month-arrows">
                    <button
                      aria-label="Previous month"
                      disabled={month <= firstMonth || loading}
                      onClick={() => changeMonth(-1)}
                    >
                      <ChevronLeft size={18} />
                    </button>
                    <button
                      aria-label="Next month"
                      disabled={month >= lastMonth || loading}
                      onClick={() => changeMonth(1)}
                    >
                      <ChevronRight size={18} />
                    </button>
                  </div>
                </div>
                <button
                  className="mobile-calendar-toggle"
                  aria-expanded={mobileMonth}
                  onClick={() => setMobileMonth(!mobileMonth)}
                >
                  <CalendarDays size={16} />
                  {mobileMonth ? "Hide month calendar" : "View month calendar"}
                </button>
                <div
                  className={`month-calendar ${mobileMonth ? "show-mobile" : ""}`}
                >
                  <div className="weekdays">
                    {["M", "T", "W", "T", "F", "S", "S"].map(
                      (letter, index) => (
                        <span
                          key={index}
                          aria-label={
                            [
                              "Monday",
                              "Tuesday",
                              "Wednesday",
                              "Thursday",
                              "Friday",
                              "Saturday",
                              "Sunday",
                            ][index]
                          }
                        >
                          {letter}
                        </span>
                      ),
                    )}
                  </div>
                  <div className="calendar-days">
                    {Array.from({ length: firstWeekday }, (_, index) => (
                      <span key={`blank${index}`} />
                    ))}
                    {Array.from({ length: daysInMonth }, (_, index) => {
                      const key = dateKey(
                        new Date(
                          month.getFullYear(),
                          month.getMonth(),
                          index + 1,
                        ),
                      );
                      const available = availableDays.includes(key);
                      return (
                        <button
                          key={key}
                          aria-label={prettyDate(key)}
                          aria-pressed={day === key}
                          className={`${available ? "available" : ""} ${day === key ? "chosen" : ""}`}
                          disabled={!available || loading}
                          onClick={() => chooseDay(key)}
                        >
                          {index + 1}
                          {available && <span className="availability-dot" />}
                        </button>
                      );
                    })}
                  </div>
                </div>
                <div className="mobile-day-strip">
                  {availableDays
                    .slice(dayPage * 5, dayPage * 5 + 5)
                    .map((key) => (
                      <button
                        key={key}
                        aria-pressed={day === key}
                        aria-label={prettyDate(key)}
                        onClick={() => chooseDay(key)}
                      >
                        <span>
                          {new Date(`${key}T12:00:00`).toLocaleDateString(
                            "en-GB",
                            { weekday: "short" },
                          )}
                        </span>
                        <strong>{Number(key.slice(-2))}</strong>
                        <span className="availability-dot" />
                      </button>
                    ))}
                  {availableDays.length > 5 && (
                    <div className="day-strip-nav">
                      <button
                        aria-label="Earlier available days"
                        disabled={dayPage === 0}
                        onClick={() => setDayPage(dayPage - 1)}
                      >
                        <ChevronLeft size={16} />
                      </button>
                      <button
                        aria-label="Later available days"
                        disabled={(dayPage + 1) * 5 >= availableDays.length}
                        onClick={() => setDayPage(dayPage + 1)}
                      >
                        <ChevronRight size={16} />
                      </button>
                    </div>
                  )}
                </div>
                <div className="calendar-legend">
                  <span className="availability-dot" /> Available for a
                  conversation
                </div>
                <div className="timezone-control">
                  <label htmlFor="timezone">
                    <Globe2 size={16} /> YOUR TIME ZONE
                  </label>
                  <select
                    id="timezone"
                    value={zone}
                    onChange={(e) => {
                      setZone(e.target.value);
                      setZoneSource("chosen");
                      setZoneNotice("");
                    }}
                  >
                    {zones.map((value) => (
                      <option value={value} key={value}>
                        {zoneName(value)} · {value}
                      </option>
                    ))}
                  </select>
                  <span className="zone-source">
                    {zoneSource === "device"
                      ? "Suggested by your device"
                      : "Selected by you"}
                    {" · Use your current travel zone"}
                  </span>
                  {zoneNotice && (
                    <span className="zone-notice" role="status">
                      {zoneNotice}
                    </span>
                  )}
                  <p>
                    All times are shown in {zoneName(zone)}.<br />
                    Ananya's time is shown alongside.
                  </p>
                </div>
              </div>
              <div className="slots-column" aria-busy={loading}>
                <div className="slots-heading">
                  <h3>{day ? prettyDate(day) : "Available times"}</h3>
                  <span>
                    {loading
                      ? "Finding a little space…"
                      : `${daySlots.length} times available · ${duration} min`}
                  </span>
                </div>
                <div className="slots-scroll" aria-live="polite">
                  {loading ? (
                    <div className="state-message">
                      <span className="loading-dot" />
                      Finding available times…
                    </div>
                  ) : error ? (
                    <div className="state-message error">
                      <strong>Schedule unavailable</strong>
                      <p>{error}</p>
                      <button onClick={() => setRetry(retry + 1)}>
                        Try again
                      </button>
                    </div>
                  ) : !daySlots.length ? (
                    <div className="state-message">
                      <CalendarDays size={26} />
                      <strong>A little space ahead</strong>
                      <p>
                        No times are available in this month. Try another month
                        or a shorter duration.
                      </p>
                    </div>
                  ) : (
                    <>
                      {renderSlots(morning, "MORNING")}
                      {renderSlots(afternoon, "AFTERNOON & EVENING")}
                    </>
                  )}
                </div>
                <p className="slot-footnote">
                  <LockKeyhole size={13} /> Your selection stays private.
                </p>
              </div>
            </div>
          </div>
        </section>
        <div className="below-panel">
          <span>
            <Check size={15} /> Time zones handled. Focus time respected.
          </span>
          <span>Thoughtfully scheduled, with PetCalendar AI.</span>
        </div>
      </main>
      <footer>
        <span>LESS BACK-AND-FORTH. MORE GOOD CONVERSATIONS.</span>
        <span>PetCalendar AI</span>
      </footer>
      {review && selected && (
        <div className="review-backdrop" onClick={() => setReview(false)}>
          <section
            className="review-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="review-title"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              autoFocus
              className="close-button"
              aria-label="Close review"
              onClick={() => setReview(false)}
            >
              <X size={20} />
            </button>
            <span className="review-icon">
              <CalendarDays size={24} />
            </span>
            <p className="eyebrow">
              {reviewStage === "timezone"
                ? "BEFORE YOU REVIEW"
                : "YOUR SELECTED TIME"}
            </p>
            <h2 id="review-title">
              {reviewStage === "timezone"
                ? "Check your current time zone."
                : "A good time to talk."}
            </h2>
            {reviewStage === "timezone" ? (
              <>
                <p>
                  Your device setting may differ while travelling. Confirm the
                  zone you want to use for this call.
                </p>
                <div className="zone-confirmation">
                  <Globe2 size={22} />
                  <div>
                    <strong>{zoneName(zone)}</strong>
                    <span>{zone}</span>
                  </div>
                </div>
                <p className="zone-confirm-copy">
                  I'm currently in this time zone, including while travelling.
                </p>
                <button
                  className="primary-button"
                  onClick={() => setReviewStage("summary")}
                >
                  Yes, confirm zone & review <ArrowRight size={16} />
                </button>
                <button
                  className="change-zone-button"
                  onClick={() => {
                    setReview(false);
                    requestAnimationFrame(() =>
                      document.getElementById("timezone")?.focus(),
                    );
                  }}
                >
                  Change my time zone
                </button>
              </>
            ) : (
              <>
                <p>
                  {event?.title} · {duration} minutes
                </p>
                <div className="review-times">
                  <div>
                    <p>YOU · {zoneName(zone).toUpperCase()}</p>
                    <strong>{timeLabel(selected.start, zone)}</strong>
                    <span>{prettyDate(selected.date)}</span>
                  </div>
                  <div>
                    <p>ANANYA · IST</p>
                    <strong>{timeLabel(selected.start, "Asia/Kolkata")}</strong>
                    <span>
                      {prettyDate(zoneDate(selected.start, "Asia/Kolkata"))}
                    </span>
                  </div>
                </div>
                <div className="review-disclosure">
                  <ShieldCheck size={18} />
                  <p>
                    This is a time selection preview. Your time has not been
                    reserved. Booking confirmation is the next functionality.
                  </p>
                </div>
                <button
                  className="primary-button"
                  onClick={() => setReview(false)}
                >
                  <ArrowLeft size={16} /> Back to available times
                </button>
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
