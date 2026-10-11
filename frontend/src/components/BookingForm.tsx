import { useId, useRef, useState } from "react";
import { useBookingContact } from "./BookingContact";
export default function BookingForm({
  endpoint,
  start,
  duration,
  timezone,
  onConflict,
}: {
  endpoint: string;
  start: string;
  duration: number;
  timezone: string;
  onConflict: () => void;
}) {
  const formId = useId();
  const contact = useBookingContact();
  const [fallbackName, setFallbackName] = useState(""),
    [fallbackEmail, setFallbackEmail] = useState("");
  const [editContact, setEditContact] = useState(false);
  const name = contact?.draft.name ?? fallbackName;
  const email = contact?.draft.email ?? fallbackEmail;
  function setName(value: string) {
    if (contact) contact.setDraft({ name: value, email });
    else setFallbackName(value);
  }
  function setEmail(value: string) {
    if (contact) contact.setDraft({ name, email: value });
    else setFallbackEmail(value);
  }
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const pending = useRef<Record<string, unknown> | null>(null);
  async function book(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    if (!pending.current) {
      const bytes = crypto.getRandomValues(new Uint8Array(32));
      pending.current = {
        start,
        duration,
        timezone,
        name: name.trim(),
        email: email.trim(),
        idempotency_key: crypto.randomUUID(),
        capability: Array.from(bytes, (b) =>
          b.toString(16).padStart(2, "0"),
        ).join(""),
      };
    }
    try {
      const response = await fetch(`${endpoint}/bookings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(pending.current),
      });
      const body = await response.json();
      if (!response.ok) {
        if (
          response.status === 409 &&
          body.error?.code !== "IDEMPOTENCY_CONFLICT"
        ) {
          pending.current = null;
          onConflict();
          return;
        }
        if (response.status === 422) pending.current = null;
        throw new Error(
          body.error?.message ||
            "Booking could not be verified. Retry with these details.",
        );
      }
      window.location.assign(
        `/booking/${body.booking.id}#${pending.current.capability}`,
      );
    } catch (e) {
      setError(
        (e as Error).message ||
          "Connection interrupted. Retry with these details.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={book} className="booking-form">
      <p>
        Your time has not been reserved. Confirm to reserve this time. Calendar
        and email delivery follow confirmation.
      </p>
      {contact?.draft.known && !editContact ? (
        <div className="booking-contact-summary">
          <p>
            <strong>Booking as {name}</strong>
            <br />
            Confirmation to {email}
          </p>
          <button
            type="button"
            className="event-secondary"
            disabled={busy || !!pending.current}
            onClick={() => setEditContact(true)}
          >
            Change booking details
          </button>
        </div>
      ) : (
        <>
          <p>
            Enter your details once for the confirmation. They stay filled while
            you choose a time on this page.
          </p>
          <label htmlFor={formId + "name"}>Your name</label>
          <input
            id={formId + "name"}
            required
            minLength={2}
            maxLength={80}
            autoComplete="name"
            value={name}
            disabled={busy || !!pending.current}
            onChange={(e) => setName(e.target.value)}
          />
          <label htmlFor={formId + "email"}>Email address</label>
          <input
            id={formId + "email"}
            type="email"
            required
            maxLength={254}
            autoComplete="email"
            value={email}
            disabled={busy || !!pending.current}
            onChange={(e) => setEmail(e.target.value)}
          />
        </>
      )}
      {error && <p role="alert">{error}</p>}
      <button className="event-primary" disabled={busy}>
        {busy
          ? "Confirming…"
          : pending.current
            ? "Retry booking confirmation"
            : "Confirm booking"}
      </button>
    </form>
  );
}
