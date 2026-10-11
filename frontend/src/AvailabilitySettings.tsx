import { useEffect, useRef, useState } from "react";
import { Plus, Trash2, ShieldCheck, Check } from "lucide-react";
import HostNavigation from "./components/HostNavigation";
import "./events.css";
import "./availability.css";
export type Hours = { start: string; end: string };
export type WeeklyHours = Hours & { weekday: number };
export type Schedule = {
  revision: number;
  timezone: string;
  enabled: boolean;
  weekly: WeeklyHours[];
  overrides: { date: string; windows: Hours[] }[];
  focus: WeeklyHours[];
  increment_minutes: number;
  host_daily_cap: number;
  weekly_cap_minutes: number;
  prefer_cluster: boolean;
};
const days = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];
export const initialSchedule = (timezone: string): Schedule => ({
  revision: 0,
  timezone,
  enabled: true,
  weekly: [0, 1, 2, 3, 4].map((weekday) => ({
    weekday,
    start: "09:00",
    end: "17:00",
  })),
  overrides: [],
  focus: [],
  increment_minutes: 15,
  host_daily_cap: 4,
  weekly_cap_minutes: 720,
  prefer_cluster: false,
});
export default function AvailabilitySettings({
  profile,
  request,
  signOut,
}: {
  profile: { display_name: string; timezone: string };
  request: (url: string, options?: RequestInit) => Promise<any>;
  signOut: () => void;
}) {
  const [form, setForm] = useState<Schedule>(initialSchedule(profile.timezone));
  const [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const requestRef = useRef(request);
  requestRef.current = request;
  async function load() {
    setLoading(true);
    setError("");
    setNotice("");
    try {
      const { schedule } = await requestRef.current("/api/me/availability");
      setForm(schedule || initialSchedule(profile.timezone));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void load();
  }, []);
  function change(update: Partial<Schedule>) {
    setForm((f) => ({ ...f, ...update }));
    setNotice("");
  }
  function editWindow(
    kind: "weekly" | "focus",
    index: number,
    update: Partial<WeeklyHours>,
  ) {
    change({
      [kind]: form[kind].map((w, i) => (i === index ? { ...w, ...update } : w)),
    });
  }
  function timeInputs(
    row: Hours,
    onChange: (v: Partial<Hours>) => void,
    label: string,
  ) {
    return (
      <>
        <input
          type="time"
          required
          aria-label={`${label} start`}
          value={row.start}
          onChange={(e) => onChange({ start: e.target.value })}
        />
        <span>to</span>
        <input
          type="time"
          required
          aria-label={`${label} end`}
          value={row.end}
          onChange={(e) => onChange({ end: e.target.value })}
        />
      </>
    );
  }
  async function save() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const { schedule } = await request("/api/me/availability", {
        method: "PUT",
        body: JSON.stringify(form),
      });
      setForm(schedule);
      setNotice(
        schedule.enabled
          ? "Availability and Focus Guard saved."
          : "Availability paused.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const zones = Array.from(
    new Set([form.timezone, "UTC", ...Intl.supportedValuesOf("timeZone")]),
  ).sort();
  return (
    <div className="events-shell">
      <HostNavigation
        profile={profile}
        current="availability"
        signOut={signOut}
      />
      <main className="events-main">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
        >
          <div className="event-title-row">
            <div>
              <span className="event-eyebrow">PROTECT YOUR TIME</span>
              <h1>Availability & Focus Guard</h1>
              <p>
                One schedule across your event types. Hours are local to the
                timezone below.
              </p>
            </div>
            <button className="event-primary" disabled={busy || loading}>
              {busy ? "Saving…" : "Save availability"}
              <Check size={18} />
            </button>
          </div>
          {loading ? (
            <p role="status">Loading availability…</p>
          ) : (
            <fieldset className="schedule-fieldset" disabled={busy}>
              <div className="event-editor-grid">
                <div className="event-section-stack">
                  <section className="event-card">
                    <h2>Schedule settings</h2>
                    <label htmlFor="schedule-zone">Schedule timezone</label>
                    <select
                      id="schedule-zone"
                      value={form.timezone}
                      onChange={(e) => change({ timezone: e.target.value })}
                    >
                      {zones.map((zone) => (
                        <option key={zone}>{zone}</option>
                      ))}
                    </select>
                    <p>
                      Changing this timezone keeps your chosen clock hours and
                      moves their UTC times. Invitees can use their own current
                      or travel timezone.
                    </p>
                    <label className="event-check">
                      <input
                        type="checkbox"
                        checked={form.enabled}
                        onChange={(e) => change({ enabled: e.target.checked })}
                      />
                      Show available times on published event pages
                    </label>
                    <label htmlFor="slot-increment">Start-time interval</label>
                    <select
                      id="slot-increment"
                      value={form.increment_minutes}
                      onChange={(e) =>
                        change({ increment_minutes: Number(e.target.value) })
                      }
                    >
                      {[5, 10, 15, 20, 30, 60].map((n) => (
                        <option key={n} value={n}>
                          {n} minutes
                        </option>
                      ))}
                    </select>
                    {form.revision === 0 && (
                      <p>
                        These suggested hours are not active until you save.
                      </p>
                    )}
                  </section>
                  <section className="event-card">
                    <h2>Weekly hours</h2>
                    {days.map((day, weekday) => (
                      <div className="weekly-day" key={day}>
                        <div className="weekly-day-heading">
                          <strong>{day}</strong>
                          <button
                            type="button"
                            className="event-secondary"
                            disabled={
                              form.weekly.filter((w) => w.weekday === weekday)
                                .length >= 3
                            }
                            onClick={() =>
                              change({
                                weekly: [
                                  ...form.weekly,
                                  { weekday, start: "09:00", end: "17:00" },
                                ],
                              })
                            }
                            aria-label={`Add ${day} hours`}
                          >
                            <Plus size={16} />
                          </button>
                        </div>
                        {form.weekly.filter((w) => w.weekday === weekday)
                          .length === 0 && <p>Unavailable</p>}
                        {form.weekly.map((row, index) =>
                          row.weekday === weekday ? (
                            <div className="schedule-time-row" key={index}>
                              {timeInputs(
                                row,
                                (v) => editWindow("weekly", index, v),
                                `${day} window ${index + 1}`,
                              )}
                              <button
                                type="button"
                                className="event-secondary schedule-remove"
                                aria-label={`Remove ${day} window ${index + 1}`}
                                onClick={() =>
                                  change({
                                    weekly: form.weekly.filter(
                                      (_, i) => i !== index,
                                    ),
                                  })
                                }
                              >
                                <Trash2 size={16} />
                              </button>
                            </div>
                          ) : null,
                        )}
                      </div>
                    ))}
                  </section>
                  <section className="event-card">
                    <h2>Date overrides</h2>
                    <p>
                      Replace weekly hours for a date, or mark the whole day
                      unavailable.
                    </p>
                    {form.overrides.map((override, index) => (
                      <div className="override-row" key={index}>
                        <div className="schedule-time-row">
                          <input
                            type="date"
                            required
                            aria-label={`Override ${index + 1} date`}
                            value={override.date}
                            onChange={(e) =>
                              change({
                                overrides: form.overrides.map((o, i) =>
                                  i === index
                                    ? { ...o, date: e.target.value }
                                    : o,
                                ),
                              })
                            }
                          />
                          <button
                            className="event-secondary schedule-remove"
                            type="button"
                            aria-label={`Remove override ${index + 1}`}
                            onClick={() =>
                              change({
                                overrides: form.overrides.filter(
                                  (_, i) => i !== index,
                                ),
                              })
                            }
                          >
                            <Trash2 size={16} />
                          </button>
                        </div>
                        <label className="event-check">
                          <input
                            type="checkbox"
                            checked={override.windows.length === 0}
                            onChange={(e) =>
                              change({
                                overrides: form.overrides.map((o, i) =>
                                  i === index
                                    ? {
                                        ...o,
                                        windows: e.target.checked
                                          ? []
                                          : [{ start: "09:00", end: "17:00" }],
                                      }
                                    : o,
                                ),
                              })
                            }
                          />
                          Unavailable all day
                        </label>
                        {override.windows.map((window, wi) => (
                          <div className="schedule-time-row" key={wi}>
                            {timeInputs(
                              window,
                              (v) =>
                                change({
                                  overrides: form.overrides.map((o, i) =>
                                    i === index
                                      ? {
                                          ...o,
                                          windows: o.windows.map((w, j) =>
                                            j === wi ? { ...w, ...v } : w,
                                          ),
                                        }
                                      : o,
                                  ),
                                }),
                              `Override ${index + 1} window ${wi + 1}`,
                            )}
                            <button
                              type="button"
                              className="event-secondary schedule-remove"
                              aria-label={`Remove override ${index + 1} window ${wi + 1}`}
                              onClick={() =>
                                change({
                                  overrides: form.overrides.map((o, i) =>
                                    i === index
                                      ? {
                                          ...o,
                                          windows: o.windows.filter(
                                            (_, j) => j !== wi,
                                          ),
                                        }
                                      : o,
                                  ),
                                })
                              }
                            >
                              <Trash2 size={16} />
                            </button>
                          </div>
                        ))}
                        {override.windows.length > 0 &&
                          override.windows.length < 3 && (
                            <button
                              type="button"
                              className="event-secondary"
                              onClick={() =>
                                change({
                                  overrides: form.overrides.map((o, i) =>
                                    i === index
                                      ? {
                                          ...o,
                                          windows: [
                                            ...o.windows,
                                            { start: "18:00", end: "20:00" },
                                          ],
                                        }
                                      : o,
                                  ),
                                })
                              }
                            >
                              Add override window
                            </button>
                          )}
                      </div>
                    ))}
                    <button
                      type="button"
                      className="event-secondary"
                      disabled={form.overrides.length >= 90}
                      onClick={() =>
                        change({
                          overrides: [
                            ...form.overrides,
                            { date: "", windows: [] },
                          ],
                        })
                      }
                    >
                      <Plus size={16} />
                      Add date override
                    </button>
                  </section>
                </div>
                <aside className="event-section-stack">
                  <section className="event-card">
                    <span className="schedule-guard-title">
                      <ShieldCheck size={20} />
                      FOCUS GUARD · ALL EVENTS
                    </span>
                    <h2>Meeting limits</h2>
                    <label htmlFor="host-cap">Max meetings per day</label>
                    <input
                      id="host-cap"
                      type="number"
                      min={1}
                      max={50}
                      required
                      value={form.host_daily_cap}
                      onChange={(e) =>
                        change({ host_daily_cap: Number(e.target.value) })
                      }
                    />
                    <label htmlFor="week-cap">Max meeting hours per week</label>
                    <input
                      id="week-cap"
                      type="number"
                      min={0}
                      max={168}
                      step={0.25}
                      required
                      value={form.weekly_cap_minutes / 60}
                      onChange={(e) =>
                        change({
                          weekly_cap_minutes: Math.round(
                            Number(e.target.value) * 60,
                          ),
                        })
                      }
                    />
                    <p>
                      Caps count actual meetings, not the number of times
                      displayed. Event-specific caps also apply.
                    </p>
                    <label className="event-check">
                      <input
                        type="checkbox"
                        checked={form.prefer_cluster}
                        onChange={(e) =>
                          change({ prefer_cluster: e.target.checked })
                        }
                      />
                      Prefer times near existing meetings
                    </label>
                    <p>
                      This recommends nearby valid times without removing other
                      choices.
                    </p>
                  </section>
                  <section className="event-card">
                    <h2>Protected focus blocks</h2>
                    <p>Recurring time you want to keep free from meetings.</p>
                    {form.focus.map((row, index) => (
                      <div className="focus-row" key={index}>
                        <select
                          aria-label={`Focus block ${index + 1} day`}
                          value={row.weekday}
                          onChange={(e) =>
                            editWindow("focus", index, {
                              weekday: Number(e.target.value),
                            })
                          }
                        >
                          {days.map((day, n) => (
                            <option key={day} value={n}>
                              {day}
                            </option>
                          ))}
                        </select>
                        <div className="schedule-time-row">
                          {timeInputs(
                            row,
                            (v) => editWindow("focus", index, v),
                            `Focus block ${index + 1}`,
                          )}
                          <button
                            type="button"
                            className="event-secondary schedule-remove"
                            aria-label={`Remove focus block ${index + 1}`}
                            onClick={() =>
                              change({
                                focus: form.focus.filter((_, i) => i !== index),
                              })
                            }
                          >
                            <Trash2 size={16} />
                          </button>
                        </div>
                      </div>
                    ))}
                    <button
                      type="button"
                      className="event-secondary"
                      disabled={form.focus.length >= 21}
                      onClick={() =>
                        change({
                          focus: [
                            ...form.focus,
                            { weekday: 0, start: "09:00", end: "11:00" },
                          ],
                        })
                      }
                    >
                      <Plus size={16} />
                      Add focus block
                    </button>
                  </section>
                  <div className="event-guard">
                    <ShieldCheck size={20} />
                    <p>
                      Duration, notice and buffers come from each event. A
                      meeting and its buffers must fit inside a working window
                      and avoid focus blocks.
                    </p>
                  </div>
                </aside>
              </div>
            </fieldset>
          )}
          {error && (
            <div className="event-error" role="alert">
              {error}
              <button
                className="event-secondary"
                type="button"
                onClick={() => void load()}
              >
                Reload saved schedule
              </button>
            </div>
          )}
          {notice && (
            <p className="event-notice" role="status">
              {notice}
            </p>
          )}
        </form>
      </main>
    </div>
  );
}
