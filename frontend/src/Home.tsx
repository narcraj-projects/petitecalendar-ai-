import {
  ArrowRight,
  CalendarDays,
  Clock3,
  Globe,
  ShieldCheck,
} from "lucide-react";
import "./home.css";
import { useState, type FormEvent } from "react";

export default function Home() {
  const [link, setLink] = useState("");
  const [error, setError] = useState("");
  function openBooking(event: FormEvent) {
    event.preventDefault();
    try {
      const url = new URL(link.trim(), window.location.origin);
      const parts = url.pathname.split("/").filter(Boolean);
      if (
        url.origin !== window.location.origin ||
        parts.length !== 2 ||
        ["api", "app", "auth", "assets", "booking", "guest", "ananya"].includes(
          parts[0],
        ) ||
        !parts.every((part) => /^[a-z0-9_-]+$/i.test(part))
      )
        throw new Error();
      window.location.assign(url.pathname);
    } catch {
      setError("Paste the PetiteCalendar-ai booking link shared by your host.");
    }
  }
  return (
    <div className="home-shell">
      <header className="home-header">
        <a className="home-brand" href="/" aria-label="PetiteCalendar-ai home">
          <CalendarDays size={28} />
          PetiteCalendar-ai
        </a>
        <a className="home-signin" href="/login">
          Host sign in <ArrowRight size={18} />
        </a>
      </header>
      <main className="home-main">
        <section className="home-hero">
          <p className="home-eyebrow">YOUR CALENDAR, WITH INTENTION</p>
          <h1>Make time for the conversations that matter.</h1>
          <p className="home-description">
            Share a booking link, protect your focus hours, and find a meeting
            time with help from your scheduling assistant.
          </p>
          <a className="home-primary" href="/login">
            Start hosting <ArrowRight size={20} />
          </a>
          <p className="home-invite">
            Booking a meeting? Open the booking link shared by your host. You
            can choose a time without creating an account.
          </p>
        </section>
        <section className="home-guest" aria-labelledby="guest-heading">
          <h2 id="guest-heading">Book as a guest</h2>
          <p>
            No sign-in needed. Open your host’s booking link, choose a time, and
            enter your own name and email before confirming.
          </p>
          <form onSubmit={openBooking}>
            <label htmlFor="guest-link">Booking link from your host</label>
            <div className="home-guest-input">
              <input
                id="guest-link"
                type="text"
                value={link}
                onChange={(event) => {
                  setLink(event.target.value);
                  setError("");
                }}
                placeholder="Paste your host’s booking link"
                required
              />
              <button className="home-primary" type="submit">
                Open booking page <ArrowRight size={18} />
              </button>
            </div>
            {error && <p role="alert">{error}</p>}
          </form>
          <p>
            Already booked?{" "}
            <a href="/guest/bookings">View your booking history</a> with an
            email sign-in link.
          </p>
        </section>
        <section className="home-features" aria-label="Scheduling features">
          <article>
            <Clock3 size={25} />
            <h2>Your availability</h2>
            <p>
              Offer meeting durations and working hours that fit your schedule.
            </p>
          </article>
          <article>
            <ShieldCheck size={25} />
            <h2>Protect your focus</h2>
            <p>Keep time between meetings and set limits on your day.</p>
          </article>
          <article>
            <Globe size={25} />
            <h2>Meet across timezones</h2>
            <p>Review the meeting in your current timezone before you book.</p>
          </article>
        </section>
      </main>
    </div>
  );
}
