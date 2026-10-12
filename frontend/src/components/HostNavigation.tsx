import { CalendarDays } from "lucide-react";
export default function HostNavigation({
  profile,
  current,
  signOut,
}: {
  profile: { display_name: string; timezone: string };
  current: "events" | "availability" | "bookings" | "integrations";
  signOut: () => void;
}) {
  return (
    <nav className="events-nav" aria-label="Host navigation">
      <a className="event-brand" href="/app/event-types">
        <CalendarDays size={24} />
        PetiteCalendar-ai
      </a>
      <a
        href="/app/bookings"
        aria-current={current === "bookings" ? "page" : undefined}
      >
        Bookings
      </a>
      <a
        href="/app/event-types"
        aria-current={current === "events" ? "page" : undefined}
      >
        Event types
      </a>
      <a
        href="/app/availability"
        aria-current={current === "availability" ? "page" : undefined}
      >
        Availability & Focus Guard
      </a>
      <a href="/app/profile">Profile & settings</a>
      <a href="/guest/bookings">My bookings as a guest</a>
      <a
        href="/app/integrations"
        aria-current={current === "integrations" ? "page" : undefined}
      >
        Calendar & Meet
      </a>
      <div className="events-nav-bottom">
        <strong>{profile.display_name}</strong>
        <p>{profile.timezone}</p>
        <button onClick={signOut}>Sign out</button>
      </div>
    </nav>
  );
}
