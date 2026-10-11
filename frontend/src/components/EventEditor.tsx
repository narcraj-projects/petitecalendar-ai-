import { useState } from "react";
import { ArrowLeft, Check, ExternalLink, ShieldCheck } from "lucide-react";

export type EventType = {
  id?: string;
  revision?: number;
  title: string;
  description: string;
  slug: string;
  durations: number[];
  default_duration: number;
  location: string;
  notice_minutes: number;
  horizon_days: number;
  buffer_before: number;
  buffer_after: number;
  max_per_day: number;
  cancellation_hours: number;
  reschedule_hours: number;
  reschedule_requires_approval: boolean;
  allow_alternatives: boolean;
  published: boolean;
};
export const blankEvent: EventType = {
  title: "",
  description: "",
  slug: "",
  durations: [30, 45, 60],
  default_duration: 45,
  location: "Online conversation",
  notice_minutes: 720,
  horizon_days: 60,
  buffer_before: 10,
  buffer_after: 15,
  max_per_day: 3,
  cancellation_hours: 12,
  reschedule_hours: 12,
  reschedule_requires_approval: false,
  allow_alternatives: true,
  published: false,
};
export default function EventEditor({
  initial,
  username,
  onSave,
  onBack,
}: {
  initial: EventType;
  username: string;
  onSave: (event: EventType) => Promise<void>;
  onBack: () => void;
}) {
  const [form, setForm] = useState<EventType>(initial);
  const [tab, setTab] = useState("Basics");
  const [durationText, setDurationText] = useState(
    initial.durations.join(", "),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [slugTouched, setSlugTouched] = useState(Boolean(initial.id));
  const change = (key: keyof EventType, value: string | number | boolean) =>
    setForm((f) => ({ ...f, [key]: value }));
  async function save() {
    setError("");
    const durations = durationText.split(",").map((v) => Number(v.trim()));
    if (
      durations.length > 6 ||
      new Set(durations).size !== durations.length ||
      durations.some((v) => !Number.isInteger(v) || v < 5 || v > 240 || v % 5)
    ) {
      setError(
        "Enter 1–6 unique durations, from 5 to 240 minutes, in five-minute increments.",
      );
      return;
    }
    if (!durations.includes(form.default_duration)) {
      setError("Default duration must be one of your duration options.");
      return;
    }
    setBusy(true);
    try {
      await onSave({ ...form, durations: durations.sort((a, b) => a - b) });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function numberField(
    key: keyof EventType,
    label: string,
    min: number,
    max: number,
  ) {
    return (
      <div>
        <label htmlFor={key}>{label}</label>
        <input
          id={key}
          type="number"
          min={min}
          max={max}
          step={1}
          required
          value={String(form[key])}
          onChange={(e) => change(key, Number(e.target.value))}
        />
      </div>
    );
  }
  return (
    <>
      <button className="event-back" onClick={onBack} disabled={busy}>
        <ArrowLeft size={16} /> Event types
      </button>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <div className="event-title-row">
          <div>
            <h1>{initial.id ? initial.title : "Create an event type"}</h1>
            <p>
              {initial.id
                ? `${initial.durations.join(" / ")} min · ${initial.published ? "Published" : "Draft"}`
                : "Start with the conversation you want to offer."}
            </p>
          </div>
          <button className="event-primary" disabled={busy}>
            {busy ? "Saving…" : initial.id ? "Save changes" : "Save draft"}
            <Check size={18} />
          </button>
        </div>
        <div className="event-tabs" aria-label="Event settings">
          {["Basics", "Limits & policies", "Publication"].map((name) => (
            <button
              type="button"
              aria-pressed={tab === name}
              key={name}
              onClick={() => setTab(name)}
            >
              {name}
            </button>
          ))}
        </div>
        <div className="event-editor-grid">
          <div className="event-section-stack">
            {tab === "Basics" && (
              <section className="event-card">
                <h2>Event details</h2>
                <label htmlFor="event-title">Event title</label>
                <input
                  id="event-title"
                  required
                  minLength={2}
                  maxLength={100}
                  value={form.title}
                  onChange={(e) => {
                    const title = e.target.value;
                    setForm((f) => ({
                      ...f,
                      title,
                      ...(!slugTouched
                        ? {
                            slug: title
                              .toLowerCase()
                              .replace(/[^a-z0-9]+/g, "-")
                              .replace(/^-|-$/g, "")
                              .slice(0, 64),
                          }
                        : {}),
                    }));
                  }}
                />
                <label htmlFor="event-description">Description</label>
                <textarea
                  id="event-description"
                  maxLength={2000}
                  rows={4}
                  value={form.description}
                  onChange={(e) => change("description", e.target.value)}
                />
                <label htmlFor="event-slug">Booking link slug</label>
                <input
                  id="event-slug"
                  required
                  minLength={3}
                  maxLength={64}
                  pattern="[a-z][a-z0-9]*(-[a-z0-9]+)*"
                  autoCapitalize="none"
                  spellCheck={false}
                  value={form.slug}
                  onChange={(e) => {
                    setSlugTouched(true);
                    change("slug", e.target.value.toLowerCase());
                  }}
                />
                <p className="event-link">
                  /{username}/{form.slug || "event-name"}
                </p>
                <div className="event-field-grid">
                  <div>
                    <label htmlFor="durations">
                      Duration options (minutes)
                    </label>
                    <input
                      id="durations"
                      required
                      value={durationText}
                      onChange={(e) => setDurationText(e.target.value)}
                    />
                    <p>Comma-separated, e.g. 30, 45, 60</p>
                  </div>
                  {numberField(
                    "default_duration",
                    "Default duration (minutes)",
                    5,
                    240,
                  )}
                </div>
                <label htmlFor="location">
                  Location or meeting instructions
                </label>
                <input
                  id="location"
                  required
                  maxLength={160}
                  value={form.location}
                  onChange={(e) => change("location", e.target.value)}
                />
                <p>Enter where invitees will meet you.</p>
              </section>
            )}
            {tab === "Limits & policies" && (
              <>
                <section className="event-card">
                  <h2>Booking limits</h2>
                  <div className="event-field-grid">
                    {numberField(
                      "notice_minutes",
                      "Minimum notice (minutes)",
                      0,
                      10080,
                    )}
                    {numberField(
                      "horizon_days",
                      "Booking horizon (days)",
                      1,
                      365,
                    )}
                    {numberField(
                      "buffer_before",
                      "Buffer before (minutes)",
                      0,
                      240,
                    )}
                    {numberField(
                      "buffer_after",
                      "Buffer after (minutes)",
                      0,
                      240,
                    )}
                    {numberField(
                      "max_per_day",
                      "Max of this event per day",
                      1,
                      50,
                    )}
                  </div>
                </section>
                <section className="event-card">
                  <h2>Reschedule & cancel policy</h2>
                  <div className="event-field-grid">
                    {numberField(
                      "reschedule_hours",
                      "Reschedule until (hours before)",
                      0,
                      720,
                    )}
                    {numberField(
                      "cancellation_hours",
                      "Cancel until (hours before)",
                      0,
                      720,
                    )}
                  </div>
                  <label className="event-check">
                    <input
                      type="checkbox"
                      checked={form.reschedule_requires_approval}
                      onChange={(e) =>
                        change("reschedule_requires_approval", e.target.checked)
                      }
                    />
                    Reschedules need my approval
                  </label>
                  <label className="event-check">
                    <input
                      type="checkbox"
                      checked={form.allow_alternatives}
                      onChange={(e) =>
                        change("allow_alternatives", e.target.checked)
                      }
                    />
                    Let me propose alternative times
                  </label>
                  <p>
                    These settings will govern booking changes when booking
                    management is available.
                  </p>
                </section>
              </>
            )}
            {tab === "Publication" && (
              <section className="event-card">
                <h2>Your public event page</h2>
                <p>
                  Drafts are private. Publishing makes your saved event details
                  visible at this link.
                </p>
                <div className="event-link">
                  {window.location.origin}/{username}/
                  {form.slug || "event-name"}
                </div>
                <label className="event-check">
                  <input
                    type="checkbox"
                    disabled={!initial.id}
                    checked={form.published}
                    onChange={(e) => change("published", e.target.checked)}
                  />
                  Publish this event
                </label>
                {!initial.id && <p>Save the draft first, then publish it.</p>}
                <p>
                  Uncheck and save to remove the public page. Changing the slug
                  changes its address; the old address stops working.
                </p>
                {initial.published && (
                  <a
                    className="event-secondary"
                    href={`/${username}/${initial.slug}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    View saved public page <ExternalLink size={16} />
                  </a>
                )}
              </section>
            )}
            {error && (
              <div role="alert" className="event-error">
                {error}
              </div>
            )}
          </div>
          <aside className="event-card event-summary">
            <span className="event-eyebrow">YOUR EVENT AT A GLANCE</span>
            <h2>{form.title || "Your next conversation"}</h2>
            <p>
              {durationText} min · {form.location}
            </p>
            <dl>
              <div>
                <dt>Notice</dt>
                <dd>{form.notice_minutes} minutes</dd>
              </div>
              <div>
                <dt>Buffers</dt>
                <dd>
                  {form.buffer_before} before / {form.buffer_after} after
                </dd>
              </div>
              <div>
                <dt>Daily event cap</dt>
                <dd>{form.max_per_day}</dd>
              </div>
            </dl>
            <div className="event-guard">
              <ShieldCheck size={20} />
              <p>
                Your published page follows your saved weekly hours and Focus
                Guard. If availability is not configured, the page shows event
                details only.
              </p>
            </div>
            <p>Changes take effect after you save.</p>
          </aside>
        </div>
      </form>
    </>
  );
}
