import { VERDICT_LABEL, verdictLabel } from "@/lib/format";
import type { Reason, Verdict } from "@/lib/types";

const STYLE: Record<Verdict, { pill: string; dot: string }> = {
  ELIGIBLE: { pill: "border-emerald-200 bg-emerald-50 text-emerald-800", dot: "bg-emerald-500" },
  CHECK_DOCS: { pill: "border-amber-200 bg-amber-50 text-amber-800", dot: "bg-amber-500" },
  NOT_ELIGIBLE: { pill: "border-rose-200 bg-rose-50 text-rose-700", dot: "bg-rose-500" },
};

/** Colour + dot + plain words ("You can bid", "Keep proof ready", "Turnover short"): never colour alone. */
export default function VerdictChip({ verdict, reasons = [], large = false }:
  { verdict: Verdict; reasons?: Reason[]; large?: boolean }) {
  const s = STYLE[verdict];
  return (
    <span title={VERDICT_LABEL[verdict]}
          className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border font-semibold ${s.pill} ${large ? "px-4 py-1.5 text-sm" : "px-3 py-1 text-xs"}`}>
      <span aria-hidden className={`inline-block h-2 w-2 rounded-full ${s.dot}`} />
      {verdictLabel(verdict, reasons)}
      <span className="sr-only"> ({VERDICT_LABEL[verdict]})</span>
    </span>
  );
}
