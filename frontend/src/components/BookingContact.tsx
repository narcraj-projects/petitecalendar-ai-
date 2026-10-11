import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { getAuthClient } from "../authClient";

type Contact = { name: string; email: string };
type Draft = Contact & { known: boolean };
const Context = createContext<{
  draft: Draft;
  setDraft: (contact: Contact) => void;
} | null>(null);

export function BookingContactProvider({ children }: { children: ReactNode }) {
  const [draft, setValue] = useState<Draft>({
    name: "",
    email: "",
    known: false,
  });
  const edited = useRef(false);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    (async () => {
      try {
        const client = await getAuthClient();
        const { data } = await client.auth.getSession();
        if (!active || !data.session) return;
        const response = await fetch("/api/me/booking-contact", {
          signal: controller.signal,
          headers: { Authorization: `Bearer ${data.session.access_token}` },
        });
        if (!response.ok) return;
        const contact: Contact = await response.json();
        if (active && !edited.current)
          setValue({
            ...contact,
            known: Boolean(contact.name && contact.email),
          });
      } catch {
        /* Optional prefill must never block guest booking. */
      }
    })();
    return () => {
      active = false;
      controller.abort();
    };
  }, []);
  return (
    <Context.Provider
      value={{
        draft,
        setDraft: (contact) => {
          edited.current = true;
          setValue({ ...contact, known: false });
        },
      }}
    >
      {children}
    </Context.Provider>
  );
}

export function useBookingContact() {
  return useContext(Context);
}
