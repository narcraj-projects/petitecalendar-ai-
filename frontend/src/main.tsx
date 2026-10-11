import { StrictMode, Suspense, lazy } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import Home from "./Home";
import PublishedEvent from "./PublishedEvent";
import BookingConfirmation from "./BookingConfirmation";
import "./styles.css";
const HostApp = lazy(() => import("./HostApp"));

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Suspense fallback={<p role="status">Loading PetiteCalendar-ai…</p>}>
      {[
        "/login",
        "/auth/callback",
        "/onboarding",
        "/app",
        "/app/profile",
        "/app/availability",
        "/app/bookings",
        "/app/integrations",
      ].includes(window.location.pathname) ||
      window.location.pathname.startsWith("/app/event-types") ? (
        <HostApp />
      ) : window.location.pathname.startsWith("/booking/") ? (
        <BookingConfirmation />
      ) : window.location.pathname === "/" ? (
        <Home />
      ) : window.location.pathname === "/ananya/career-strategy" ? (
        <App />
      ) : (
        <PublishedEvent />
      )}
    </Suspense>
  </StrictMode>,
);
