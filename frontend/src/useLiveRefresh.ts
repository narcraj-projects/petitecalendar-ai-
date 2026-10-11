import { useEffect, useState } from "react";

const CHANGE_EVENT = "petcalendar:booking-changed";
const CHANGE_KEY = "petcalendar:booking-refresh";
export const REFRESH_INTERVAL_MS = 15_000;

export function notifyBookingChanged() {
  window.dispatchEvent(new Event(CHANGE_EVENT));
  try {
    // Only an invalidation marker is shared, never booking or contact details.
    localStorage.setItem(CHANGE_KEY, `${Date.now()}-${Math.random()}`);
  } catch {
    // Private browsers can deny storage; focus and polling still refresh.
  }
}

export function useLiveRefresh() {
  const [version, setVersion] = useState(0);
  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState === "visible" && navigator.onLine)
        setVersion((value) => value + 1);
    };
    const storage = (event: StorageEvent) => {
      if (event.key === CHANGE_KEY) refresh();
    };
    const timer = window.setInterval(refresh, REFRESH_INTERVAL_MS);
    window.addEventListener(CHANGE_EVENT, refresh);
    window.addEventListener("storage", storage);
    window.addEventListener("focus", refresh);
    window.addEventListener("online", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener(CHANGE_EVENT, refresh);
      window.removeEventListener("storage", storage);
      window.removeEventListener("focus", refresh);
      window.removeEventListener("online", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, []);
  return version;
}
