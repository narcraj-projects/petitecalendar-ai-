import { useEffect, useRef, useState } from "react";
import type { EventType } from "./EventEditor";
import { useLiveRefresh } from "../useLiveRefresh";
import "../share.css";

type Batch = { id: string; counts: Record<string, number> };
export default function ShareEvent({
  event,
  host,
  request,
  onClose,
}: {
  event: EventType;
  host: { display_name: string; username: string };
  request: (url: string, options?: RequestInit) => Promise<any>;
  onClose: () => void;
}) {
  const [input, setInput] = useState("");
  const [recipients, setRecipients] = useState<string[]>([]);
  const [review, setReview] = useState(false);
  const [batch, setBatch] = useState<Batch>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const pending = useRef<
    | {
        revision: number;
        recipients: string[];
        idempotency_key: string;
      }
    | undefined
  >(undefined);
  const refresh = useLiveRefresh();
  const endpoint = `/api/me/event-types/${event.id}/invitations`;
  const link = `${window.location.origin}/${host.username}/${event.slug}`;
  function prepare(e: React.FormEvent) {
    e.preventDefault();
    const values = input
      .split(/[\s,;]+/)
      .filter(Boolean)
      .map((s) => s.toLowerCase())
      .sort();
    if (
      !values.length ||
      values.length > 10 ||
      new Set(values).size !== values.length ||
      values.some(
        (s) => s.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s),
      )
    ) {
      setError(
        "Enter 1-10 unique email addresses, separated by commas or new lines.",
      );
      return;
    }
    setRecipients(values);
    setReview(true);
    setError("");
  }
  async function send() {
    setBusy(true);
    setError("");
    pending.current ||= {
      revision: event.revision!,
      recipients,
      idempotency_key: crypto.randomUUID(),
    };
    try {
      const result = await request(endpoint, {
        method: "POST",
        body: JSON.stringify(pending.current),
      });
      setBatch(result.invitation);
    } catch (e) {
      const status = (e as Error & { status?: number }).status;
      if (status && status < 500) pending.current = undefined;
      setError(
        (e as Error).message ||
          "Could not verify sharing. Retry the same invitation.",
      );
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    if (!batch) return;
    let active = true;
    request(`${endpoint}/${batch.id}`)
      .then((result) => {
        if (active) {
          setBatch(result.invitation);
          setError("");
        }
      })
      .catch(() => {
        if (active)
          setError(
            "Status could not refresh. Your invitation remains queued; retrying automatically.",
          );
      });
    return () => {
      active = false;
    };
  }, [refresh, batch?.id]);
  const accepted = batch?.counts.accepted || 0;
  const waiting =
    (batch?.counts.queued || 0) +
    (batch?.counts.working || 0) +
    (batch?.counts.retry || 0);
  return (
    <section className="event-card share-event" aria-labelledby="share-heading">
      <div className="share-heading">
        <h2 id="share-heading">Share {event.title} by email</h2>
        <button className="event-secondary" disabled={busy} onClick={onClose}>
          Close sharing
        </button>
      </div>
      <p>
        Invite guests to choose a time. Sending this link does not reserve a
        slot.
      </p>
      {batch ? (
        <div role="status">
          <p>
            <strong>Invitations queued.</strong> {accepted} accepted by the
            email service · {waiting} waiting.
          </p>
          {!!batch.counts.failed && (
            <p>
              {batch.counts.failed} could not be sent. Check the addresses and
              sender configuration.
            </p>
          )}
          {!!batch.counts.uncertain && (
            <p>
              {batch.counts.uncertain} have uncertain delivery. Check Resend
              before sending another invitation.
            </p>
          )}
          <p>Provider acceptance does not guarantee inbox delivery.</p>
        </div>
      ) : !review ? (
        <form onSubmit={prepare}>
          <label htmlFor="share-recipients">Guest email addresses</label>
          <textarea
            id="share-recipients"
            rows={3}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="guest@example.com, another@example.com"
            required
          />
          <p>
            Up to 10 recipients per invitation and 20 per host per UTC day. Each
            guest receives a separate email.
          </p>
          <button className="event-primary" type="submit">
            Review invitation
          </button>
        </form>
      ) : (
        <>
          <h3>Review recipients</h3>
          <ul>
            {recipients.map((email) => (
              <li key={email}>{email}</li>
            ))}
          </ul>
          <p>
            Booking link: <a href={link}>{link}</a>
          </p>
          <div
            className="share-email-preview"
            aria-label="Invitation email preview"
          >
            <span className="event-eyebrow">PetiteCalendar-ai</span>
            <h3>A conversation worth making time for.</h3>
            <p>
              Hi,
              <br />
              <strong>{host.display_name}</strong> would love to find a time to
              connect with you.
            </p>
            <div className="share-email-details">
              <strong>{event.title}</strong>
              <p>Duration options: {event.durations.join(", ")} minutes</p>
            </div>
            <p>
              Choose a time that works for you. You’ll review it in your current
              timezone before confirming.
            </p>
            <a
              className="event-primary"
              href={link}
              target="_blank"
              rel="noreferrer"
            >
              Choose a time
            </a>
            <p>
              No account needed. Enter your own name and email when you book.
              This invitation has not reserved a time.
            </p>
          </div>
          <div className="event-card-actions">
            <button
              className="event-primary"
              disabled={busy}
              onClick={() => void send()}
            >
              {busy
                ? "Sending…"
                : pending.current
                  ? "Retry same invitation"
                  : "Send booking link"}
            </button>
            <button
              className="event-secondary"
              disabled={busy || !!pending.current}
              onClick={() => setReview(false)}
            >
              Edit recipients
            </button>
          </div>
        </>
      )}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
