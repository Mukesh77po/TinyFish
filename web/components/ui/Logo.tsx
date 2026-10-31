import Link from "next/link";

/** The amber TenderHawk mark and wordmark (Stitch header). Inline SVG: no image request, works offline. */
export default function Logo({ href = "/", size = "md" }: { href?: string; size?: "md" | "sm" }) {
  const box = size === "md" ? "h-9 w-9" : "h-8 w-8";
  return (
    <Link href={href} className="flex items-center gap-3">
      <span aria-hidden className={`${box} flex items-center justify-center rounded-lg bg-gradient-to-tr from-amber-500 to-amber-400 p-1 text-slate-950 shadow-sm shadow-amber-500/20`}>
        <svg viewBox="0 0 24 24" className="h-5 w-5 fill-current">
          <path d="M21 7.28V5c0-1.1-.9-2-2-2H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2v-2.28c.59-.35 1-.99 1-1.72V9c0-.73-.41-1.37-1-1.72zM20 9v6h-7V9h7zM5 19V5h14v2h-6c-1.1 0-2 .9-2 2v6c0 1.1.9 2 2 2h6v2H5z" />
        </svg>
      </span>
      <span className={`font-heading font-bold tracking-tight text-white ${size === "md" ? "text-xl" : "text-lg"}`}>TenderHawk</span>
    </Link>
  );
}
