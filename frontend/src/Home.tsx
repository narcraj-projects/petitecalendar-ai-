import {
  ArrowRight,
  CalendarDays,
  Clock3,
  Globe,
  ShieldCheck,
} from "lucide-react";
import "./home.css";

export default function Home() {
  return (
    <div className="home-shell">
      <header className="home-header">
        <a className="home-brand" href="/" aria-label="PetCalendar AI home">
          <CalendarDays size={28} />
          PetCalendar AI
        </a>
        <a className="home-signin" href="/login">
          Sign in <ArrowRight size={18} />
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
            Get started <ArrowRight size={20} />
          </a>
          <p className="home-invite">
            Booking a meeting? Open the booking link shared by your host. You
            can choose a time without creating an account.
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
