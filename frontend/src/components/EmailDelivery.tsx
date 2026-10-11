const labels: Record<string, string> = {
  not_enabled: "Email: not enabled. No invitation has been sent yet.",
  queued: "Email confirmation queued",
  working: "Sending email confirmation",
  retry: "Email confirmation retrying",
  accepted:
    "Email accepted by the email service. Check your inbox and spam folder.",
  failed:
    "Email could not be sent. Your booking remains confirmed; keep this private link.",
  uncertain:
    "Email status is uncertain. Check your inbox; your booking remains confirmed.",
};
export default function EmailDelivery({ status }: { status: string }) {
  return <p>{labels[status] || "Email status unavailable"}</p>;
}
