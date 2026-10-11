import "../integrations.css";
const states: Record<string, string> = {
  not_connected: "Calendar not connected",
  queued: "Calendar delivery queued",
  working: "Creating calendar event / Meet",
  retry: "Calendar delivery retrying",
  synced: "Calendar event created",
  failed: "Calendar delivery needs attention",
};
export default function CalendarDelivery({
  status,
  meetUrl,
  cancelled = false,
}: {
  status: string;
  meetUrl?: string | null;
  cancelled?: boolean;
}) {
  const safeLink =
    meetUrl && /^https:\/\/meet\.google\.com\/[a-z0-9-]+$/.test(meetUrl)
      ? meetUrl
      : null;
  return (
    <div className="calendar-delivery">
      <span>
        {cancelled && status === "synced"
          ? "Calendar event removed"
          : cancelled && ["queued", "working", "retry"].includes(status)
            ? "Calendar removal pending"
            : states[status] || "Calendar status unavailable"}
      </span>
      {safeLink && !cancelled && (
        <a href={safeLink} target="_blank" rel="noopener noreferrer">
          Join Google Meet
        </a>
      )}
    </div>
  );
}
