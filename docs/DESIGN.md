# PetiteCalendar-ai design system – "Midnight"

Dark-first, high-contrast, product-led. One loud colour (lime) for the main action; amber means "protection"
(Focus Guard, cancellation policy). Everything else is quiet greys.

## Colour tokens

| Token | Hex | Use |
| --- | --- | --- |
| `bg` | #0D0F14 | Page background |
| `surface` | #151922 | Cards, panels, sidebar, inputs |
| `raised` | #1E2330 | Available calendar days, chips, inner tiles |
| `border` | #262B36 | Card borders, dividers |
| `border-strong` | #343A48 | Outline buttons, slot buttons, inputs |
| `text` | #EEF0F4 | Primary text |
| `muted` | #9AA1AE | Secondary text, host time next to slot |
| `dim` | #7E8696 | Small uppercase labels (MORNING, weekday letters) |
| `disabled` | #4A5060 | Unavailable days |
| `accent` | #C8F25C | Primary buttons, selected day, availability dots, links. Text on it is #0D0F14 |
| `accent-tint` | #1A2110 | Accent banners (Mutual Match). Border #3D4A1E, body text #C7CDB8 |
| `guard` | #FFB547 | Focus Guard labels, caps reached, policy |
| `guard-tint` | #2A2416 | Amber banners and chips. Text on it #FFD08A |

Hosts may override `accent` for their own booking page; keep text on it dark.

## Typography

- Headings: **Space Grotesk** 500/700, letter-spacing -0.01em to -0.03em. Page title 34–48px, section 20–22px.
- Body/UI: **Manrope** 400–800. Body 15–16px, labels 13–14px, small caps labels 12px bold with 0.06–0.08em tracking.
- Load both from Google Fonts via `next/font/google`.

## Shape and spacing

- Radius: 12px buttons/slots, 14px day cells, 16–20px cards, 24px main booking panel, full pill for duration toggles.
- Spacing scale: 4, 6, 8, 10, 12, 14, 16, 20, 24, 28px. Page max width 1180px.
- Minimum touch target 44px; slot buttons 48–60px tall.
- No shadows, no gradients. Depth comes from the bg → surface → raised steps.

## Key components

- **DurationToggle**: pills; selected = solid `text` background with `bg` text.
- **MonthCalendar**: 7-col grid; available day = `raised` with a 5px lime dot; selected = lime fill; unavailable = `disabled` text, not clickable.
- **SlotList**: grouped MORNING / AFTERNOON; each row shows invitee time (bold) + host time (muted). Selecting a slot splits it into [time] [Next →] (lime).
- **MutualMatchBanner**: accent-tint banner, "Showing times you're both free… nothing is saved".
- **TimezoneLine**: globe icon + "London (BST) · Ananya is 4 h 30 ahead".
- **StatusChip**: good = lime on accent-tint; warning = #FFD08A on guard-tint.
- **FocusGuardBar**: per-day bars against the daily cap; a day at cap turns amber.
- Icons: lucide-react, 1.8–2px stroke.

## Tailwind setup (tailwind.config.ts → theme.extend)

```ts
colors: {
  bg: '#0D0F14', surface: '#151922', raised: '#1E2330',
  border: { DEFAULT: '#262B36', strong: '#343A48' },
  text: { DEFAULT: '#EEF0F4', muted: '#9AA1AE', dim: '#7E8696', disabled: '#4A5060' },
  accent: { DEFAULT: '#C8F25C', tint: '#1A2110', ink: '#0D0F14' },
  guard: { DEFAULT: '#FFB547', tint: '#2A2416', text: '#FFD08A' },
},
fontFamily: {
  display: ['var(--font-space-grotesk)', 'system-ui', 'sans-serif'],
  sans: ['var(--font-manrope)', 'system-ui', 'sans-serif'],
},
borderRadius: { slot: '12px', day: '14px', card: '20px', panel: '24px' },
```

Map shadcn/ui CSS variables to these tokens in `globals.css` (`--background`, `--card`, `--primary`, `--border`, etc.).

## Screen → route map

| Reference file | Route | Notes |
| --- | --- | --- |
| 01-booking-desktop.html | `/{username}/{slug}` | Desktop layout; host info left, calendar + slots right |
| 02-booking-mobile-mutual-match.html | `/{username}/{slug}` (mobile) | Day strip instead of month grid; Mutual Match on |
| 03-confirmation-mobile.html | `/booking/{uid}` | Both time zones, WhatsApp opt-in, reschedule/cancel |
| 04-host-dashboard.html | `/app/bookings` | Sidebar + Focus Guard week bar + bookings table |
| 05-event-type-editor.html | `/app/event-types/{id}` | "Limits & policies" tab |

Screens not drawn yet (onboarding, availability, polls, landing): follow this file and the closest reference screen.
