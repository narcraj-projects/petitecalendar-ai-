import { useRef, useState } from "react";
import { bookingTime, type SavedBooking } from "../BookingConfirmation";
import AvailabilityPicker from "./AvailabilityPicker";
import AssistantPanel from "./AssistantPanel";

type Command = {
  action: string;
  revision: number;
  idempotency_key: string;
  candidates?: string[];
  timezone?: string;
  request_id?: string;
};

export default function BookingManagement({
  booking,
  capability,
  onSaved,
  hostRequest,
}: {
  booking: SavedBooking;
  capability?: string;
  onSaved: (booking: SavedBooking) => void;
  hostRequest?: (url: string, options?: RequestInit) => Promise<any>;
}) {
  const [mode, setMode] = useState(""),
    [choices, setChoices] = useState<string[]>([]);
  const [zone, setZone] = useState(booking.invitee_timezone),
    [error, setError] = useState("");
  const [busy, setBusy] = useState(false),
    [uncertain, setUncertain] = useState(false);
  const [message, setMessage] = useState("");
  const command = useRef<Command | null>(null);
  const host = Boolean(hostRequest),
    pending = booking.change_request?.status === "pending";
  const deadline = (hours: number) =>
    new Date(booking.start_at).getTime() - (host ? 0 : hours * 3600000) >
    Date.now();
  const canCancel =
    booking.status === "confirmed" &&
    deadline(booking.snapshot.cancellation_hours);
  const canMove =
    booking.status === "confirmed" &&
    deadline(booking.snapshot.reschedule_hours);
  const approval = !host && booking.snapshot.reschedule_requires_approval;
  const maxChoices = approval && booking.snapshot.allow_alternatives ? 3 : 1;

  async function send(action: string, candidates?: string[]) {
    command.current ||= {
      action,
      revision: booking.revision,
      idempotency_key: crypto.randomUUID(),
      candidates: candidates || [],
      timezone: zone,
      request_id: ["approve", "decline", "withdraw"].includes(action)
        ? booking.change_request?.id
        : undefined,
    };
    setBusy(true);
    setError("");
    try {
      const endpoint = `${host ? "/api/me" : "/api"}/bookings/${booking.id}/actions`;
      let data;
      if (hostRequest)
        data = await hostRequest(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(command.current),
        });
      else {
        const r = await fetch(endpoint, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Booking-Capability": capability || "",
          },
          body: JSON.stringify(command.current),
        });
        data = await r.json();
        if (!r.ok) {
          if (r.status < 500) {
            command.current = null;
            setUncertain(false);
          }
          throw new Error(
            data.error?.message || "The action could not be verified.",
          );
        }
      }
      const originalAction = command.current?.action;
      command.current = null;
      setUncertain(false);
      setMode("");
      setChoices([]);
      onSaved(data.booking);
      setMessage(
        originalAction === "reschedule" &&
          data.booking.change_request?.status === "pending"
          ? "Request sent. Your original time stays reserved until the host approves. Proposed times are not held."
          : originalAction === "cancel"
            ? "Booking cancelled. Your time has been released."
            : originalAction === "decline" || originalAction === "withdraw"
              ? "Request closed. Your original time is unchanged."
              : "Booking rescheduled. Your new time is reserved.",
      );
    } catch (e) {
      if (
        (e as Error & { status?: number }).status &&
        (e as Error & { status: number }).status < 500
      )
        command.current = null;
      setUncertain(Boolean(command.current));
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="event-card booking-management">
      <h2>{host ? "Manage booking" : "Change your booking"}</h2>
      {booking.status === "confirmed" && !uncertain && (
        <AssistantPanel
          key={booking.id + "-" + booking.revision}
          endpoint={`${host ? "/api/me" : "/api"}/bookings/${booking.id}/assistant`}
          request={hostRequest}
          headers={
            host ? undefined : { "X-Booking-Capability": capability || "" }
          }
          timezone={booking.invitee_timezone}
          duration={booking.duration}
          onSaved={(body) => onSaved(body.booking)}
          onSelect={(start, timezone) => {
            setChoices([start]);
            setZone(timezone);
            setMode("reschedule");
            setError("");
            command.current = null;
          }}
        />
      )}
      {message && <p role="status">{message}</p>}
      {error && <p role="alert">{error}</p>}
      {uncertain ? (
        <>
          <p>
            The outcome is not verified. Retry the same action before making
            another change.
          </p>
          <button
            className="event-primary"
            disabled={busy}
            onClick={() => void send(command.current!.action)}
          >
            Retry same action
          </button>
        </>
      ) : (
        <>
          {booking.change_request && (
            <div className="management-request">
              <h3>Reschedule request · {booking.change_request.status}</h3>
              <p>
                {pending
                  ? "The original booking remains reserved. These proposed times are not held."
                  : "Your booking details above show the current time."}
              </p>
              {booking.change_request.candidates.map((start) => (
                <p key={start}>
                  {bookingTime(start, booking.change_request!.timezone)}
                  <br />
                  Host: {bookingTime(start, booking.snapshot.host_timezone)}
                </p>
              ))}
              {pending &&
                (host ? (
                  <>
                    {booking.change_request.candidates.map((start) => (
                      <button
                        key={start}
                        className="event-secondary"
                        disabled={busy || !canMove}
                        onClick={() => {
                          setChoices([start]);
                          setZone(booking.change_request!.timezone);
                          setMode("approve");
                        }}
                      >
                        Review approval ·{" "}
                        {bookingTime(start, booking.snapshot.host_timezone)}
                      </button>
                    ))}
                    <button
                      className="event-secondary"
                      disabled={busy}
                      onClick={() => setMode("decline")}
                    >
                      Review decline
                    </button>
                  </>
                ) : (
                  <button
                    className="event-secondary"
                    disabled={busy}
                    onClick={() => setMode("withdraw")}
                  >
                    Withdraw request
                  </button>
                ))}
            </div>
          )}
          {!mode && (
            <div className="management-actions">
              <button
                className="event-primary"
                disabled={!canMove || pending || busy}
                onClick={() => {
                  setMode("reschedule");
                  setChoices([]);
                }}
              >
                Reschedule booking
              </button>
              <button
                className="event-secondary"
                disabled={!canCancel || busy}
                onClick={() => setMode("cancel")}
              >
                Cancel booking
              </button>
            </div>
          )}
          {booking.status === "confirmed" && !canCancel && (
            <p>The cancellation deadline has passed.</p>
          )}
          {booking.status === "confirmed" && !host && !canMove && (
            <p>The rescheduling deadline has passed.</p>
          )}
          {mode === "reschedule" && (
            <>
              <p>
                {approval
                  ? `Choose up to ${maxChoices} ${maxChoices === 1 ? "time" : "alternative times"} for host approval.`
                  : "Choose a replacement time. Review it before confirming."}
              </p>
              <AvailabilityPicker
                duration={booking.duration}
                hostZone={booking.snapshot.host_timezone}
                endpoint={`${host ? "/api/me" : "/api"}/bookings/${booking.id}`}
                request={hostRequest}
                headers={{ "X-Booking-Capability": capability || "" }}
                onSelect={(start, selectedZone) => {
                  if (
                    zone === selectedZone &&
                    maxChoices > 1 &&
                    choices.length >= maxChoices &&
                    !choices.includes(start)
                  ) {
                    setError(
                      `Remove a proposed time before adding another. You can choose up to ${maxChoices}.`,
                    );
                    return;
                  }
                  setError("");
                  setChoices((previous) =>
                    zone !== selectedZone
                      ? [start]
                      : maxChoices === 1
                        ? [start]
                        : previous.includes(start)
                          ? previous
                          : previous.length < maxChoices
                            ? [...previous, start]
                            : previous,
                  );
                  setZone(selectedZone);
                }}
              />
              {choices.length > 0 && (
                <div className="management-review">
                  <h3>
                    Review replacement {choices.length > 1 ? "times" : "time"}
                  </h3>
                  {choices.map((start) => (
                    <div key={start}>
                      <p>
                        Your time: {bookingTime(start, zone)} · {zone}
                        <br />
                        Host:{" "}
                        {bookingTime(
                          start,
                          booking.snapshot.host_timezone,
                        )} · {booking.snapshot.host_timezone}
                        <br />
                        {booking.duration} minutes
                      </p>
                      <button
                        className="event-secondary"
                        onClick={() =>
                          setChoices(choices.filter((s) => s !== start))
                        }
                      >
                        Remove time
                      </button>
                    </div>
                  ))}
                  <button
                    className="event-primary"
                    disabled={busy}
                    onClick={() => void send("reschedule", choices)}
                  >
                    {busy
                      ? "Verifying change…"
                      : approval
                        ? "Confirm reschedule request"
                        : "Confirm reschedule"}
                  </button>
                </div>
              )}
              <button
                className="event-secondary"
                disabled={busy}
                onClick={() => setMode("")}
              >
                Keep original booking
              </button>
            </>
          )}
          {["cancel", "approve", "decline", "withdraw"].includes(mode) && (
            <div className="management-review">
              <h3>
                {mode === "cancel"
                  ? "Confirm cancellation"
                  : mode === "approve"
                    ? "Confirm replacement time"
                    : mode === "decline"
                      ? "Decline this request?"
                      : "Withdraw this request?"}
              </h3>
              <p>
                {mode === "cancel"
                  ? "This releases your reserved time and queues removal of the Google Calendar event."
                  : mode === "approve"
                    ? `New time: ${bookingTime(choices[0], zone)}. The original time is replaced only if the new time is still available.`
                    : "The original booking stays reserved."}
              </p>
              <button
                className="event-primary"
                disabled={busy}
                onClick={() =>
                  void send(mode, mode === "approve" ? choices : [])
                }
              >
                {busy
                  ? "Verifying change…"
                  : mode === "cancel"
                    ? "Yes, cancel booking"
                    : mode === "approve"
                      ? "Approve requested time"
                      : mode === "decline"
                        ? "Confirm decline"
                        : "Confirm withdrawal"}
              </button>
              <button
                className="event-secondary"
                disabled={busy}
                onClick={() => setMode("")}
              >
                Go back
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
