import { useEffect, useState } from "react";
import { CalendarDays, Check } from "lucide-react";
import "./events.css";
import "./bookings.css";
import CalendarDelivery from "./components/CalendarDelivery";
import EmailDelivery from "./components/EmailDelivery";
import BookingManagement from "./components/BookingManagement";
import { useLiveRefresh } from "./useLiveRefresh";
export type SavedBooking = {
  id: string;
  start_at: string;
  end_at: string;
  duration: number;
  invitee_name: string;
  invitee_email: string;
  invitee_timezone: string;
  status: string;
  revision: number;
  snapshot: {
    title: string;
    location: string;
    host_name: string;
    host_timezone: string;
    cancellation_hours: number;
    reschedule_hours: number;
    reschedule_requires_approval?: boolean;
    allow_alternatives?: boolean;
  };
  calendar_status: string;
  email_status: string;
  meet_url?: string | null;
  change_request?: {
    id: string;
    booking_revision: number;
    candidates: string[];
    timezone: string;
    status: string;
  } | null;
};
export const bookingTime = (instant: string, zone: string) =>
  new Intl.DateTimeFormat("en-GB", {
    timeZone: zone,
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "shortOffset",
  }).format(new Date(instant));
const privateCapability = window.location.hash.slice(1);
const bookingPath = window.location.pathname;
export default function BookingConfirmation() {
  const refresh = useLiveRefresh();
  const [refreshError, setRefreshError] = useState("");
  const [booking, setBooking] = useState<SavedBooking>(),
    [error, setError] = useState(""),
    [retry, setRetry] = useState(0),
    [copied, setCopied] = useState(false);
  const [downloading, setDownloading] = useState(false),
    [downloadError, setDownloadError] = useState("");
  async function downloadCalendar() {
    if (!booking) return;
    setDownloading(true);
    setDownloadError("");
    try {
      const response = await fetch(`/api/bookings/${booking.id}/calendar.ics`, {
        headers: { "X-Booking-Capability": privateCapability },
      });
      if (!response.ok)
        throw new Error("Calendar download failed. Please retry.");
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = `booking-${booking.id}.ics`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setDownloadError((e as Error).message);
    } finally {
      setDownloading(false);
    }
  }
  useEffect(() => {
    const controller = new AbortController();
    setError("");
    fetch(`/api/bookings/${bookingPath.split("/").pop()}`, {
      headers: { "X-Booking-Capability": privateCapability },
      signal: controller.signal,
    })
      .then(async (r) => {
        const body = await r.json();
        if (!r.ok)
          throw new Error(
            body.error?.message || "Booking could not be loaded.",
          );
        setBooking(body.booking);
        setRefreshError("");
      })
      .catch((e) => {
        if (e.name !== "AbortError") {
          if (booking)
            setRefreshError(
              "Updates could not be loaded. Retrying automatically.",
            );
          else setError(e.message);
        }
      });
    return () => controller.abort();
  }, [retry, refresh]);
  return (
    <div className="published-shell">
      <header>
        <a className="event-brand" href="/login">
          <CalendarDays size={24} />
          PetiteCalendar-ai
        </a>
        <span>Private booking</span>
      </header>
      <main className="confirmation-main">
        {refreshError && <p role="status">{refreshError}</p>}
        {error ? (
          <section className="event-card">
            <h1>Booking unavailable</h1>
            <p role="alert">{error}</p>
            <button
              className="event-secondary"
              onClick={() => setRetry(retry + 1)}
            >
              Retry
            </button>
          </section>
        ) : !booking ? (
          <p role="status">Loading your booking…</p>
        ) : (
          <>
            <div className="confirmation-heading">
              <span className="confirmation-check">
                <Check size={28} />
              </span>
              <h1>
                {booking.status === "cancelled"
                  ? "Booking cancelled."
                  : "You’re booked."}
              </h1>
              <p>
                {booking.status === "cancelled"
                  ? "Your time has been released."
                  : "Your time is reserved."}{" "}
                Keep this private link to return to your booking.
              </p>
            </div>
            <section className="event-card">
              <h2>{booking.snapshot.title}</h2>
              <div className="booking-zones">
                <div>
                  <small>YOU · {booking.invitee_timezone}</small>
                  <strong>
                    {bookingTime(booking.start_at, booking.invitee_timezone)}
                  </strong>
                </div>
                <div>
                  <small>
                    {booking.snapshot.host_name} ·{" "}
                    {booking.snapshot.host_timezone}
                  </small>
                  <strong>
                    {bookingTime(
                      booking.start_at,
                      booking.snapshot.host_timezone,
                    )}
                  </strong>
                </div>
              </div>
              <p>
                {booking.duration} minutes · {booking.snapshot.location}
              </p>
              <p>
                {booking.invitee_name} · {booking.invitee_email}
              </p>
              <span className="booking-status">{booking.status}</span>
            </section>
            <section className="event-card">
              <h2>Booking details</h2>
              <CalendarDelivery
                status={booking.calendar_status}
                meetUrl={booking.meet_url}
                cancelled={booking.status === "cancelled"}
              />
              <button
                className="event-secondary"
                onClick={() => setRetry(retry + 1)}
              >
                Refresh calendar status
              </button>
              <EmailDelivery status={booking.email_status} />
              <button
                className="event-secondary"
                onClick={() => setRetry(retry + 1)}
              >
                Refresh email status
              </button>
              <button
                className="event-primary"
                disabled={downloading}
                onClick={() => void downloadCalendar()}
              >
                {downloading
                  ? "Downloading calendar…"
                  : "Download calendar (.ics)"}
              </button>
              {downloadError && <p role="alert">{downloadError}</p>}
              <p>
                The calendar file uses your saved meeting time. Download again
                after Meet is ready to include its link.
              </p>
              <p>
                Saved policy: cancellation until{" "}
                {bookingTime(
                  new Date(
                    new Date(booking.start_at).getTime() -
                      booking.snapshot.cancellation_hours * 3600000,
                  ).toISOString(),
                  booking.invitee_timezone,
                )}
                . Rescheduling until{" "}
                {bookingTime(
                  new Date(
                    new Date(booking.start_at).getTime() -
                      booking.snapshot.reschedule_hours * 3600000,
                  ).toISOString(),
                  booking.invitee_timezone,
                )}
                .
              </p>
              <button
                className="event-primary"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(
                      `${window.location.origin}${bookingPath}#${privateCapability}`,
                    );
                    setCopied(true);
                  } catch {
                    setCopied(false);
                    setError(
                      "Copy is unavailable. Save this page’s private URL.",
                    );
                  }
                }}
              >
                {copied ? "Private link copied" : "Copy private booking link"}
              </button>
              <p>
                This link grants access to your booking details. Share it only
                with someone you trust.
              </p>
            </section>
            <BookingManagement
              booking={booking}
              capability={privateCapability}
              onSaved={setBooking}
            />
          </>
        )}
      </main>
    </div>
  );
}
