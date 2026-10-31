import { parseRupees, splitList } from "./format";
import type { ProfileInput } from "./types";

export const EMPTY = { name: "", phone: "", email: "", products: "", keywords: "", hsn: "", turnover: "", years: "",
                certs: [] as string[], otherCerts: "", states: "" };

export type FormState = typeof EMPTY;

export function toProfileInput(f: FormState): { input?: ProfileInput; error?: string } {
  if (!f.name.trim()) return { error: "Business name is required." };
  const turnover = f.turnover.trim() ? parseRupees(f.turnover) : null;
  if (f.turnover.trim() && turnover == null) return { error: "Turnover: write it like 1.2 Cr, 40 lakh or 1200000." };
  const years = f.years.trim() ? Number(f.years) : null;
  if (years != null && (!Number.isInteger(years) || years < 0)) return { error: "Years in business must be a whole number." };
  const products = splitList(f.products);
  const keywords = splitList(f.keywords);
  if (!products.length && !keywords.length) return { error: "Add at least one product or search keyword." };
  return {
    input: {
      name: f.name.trim(), phone: f.phone.trim() || null, email: f.email.trim() || null,
      products, keywords, hsn_codes: splitList(f.hsn), annual_turnover: turnover, years_in_business: years,
      certifications: [...f.certs, ...splitList(f.otherCerts)], states_served: splitList(f.states),
    },
  };
}
