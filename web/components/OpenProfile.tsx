"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export default function OpenProfile() {
  const router = useRouter();
  const [id, setId] = useState("1");
  return (
    <form id="open" onSubmit={(e) => { e.preventDefault(); if (/^\d+$/.test(id)) router.push(`/profiles/${id}`); }}
          className="flex scroll-mt-24 flex-wrap items-end gap-3 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <label className="flex flex-col gap-1">
        <span className="text-sm font-semibold text-slate-900">Open an existing profile</span>
        <input aria-label="Profile id" value={id} onChange={(e) => setId(e.target.value.trim())} inputMode="numeric"
               className="h-10 w-28 rounded-xl border border-slate-200 bg-white px-3 text-sm focus:border-blue-600 focus:outline-none focus:ring-4 focus:ring-blue-600/10" />
      </label>
      <button className="h-10 rounded-xl bg-navy px-4 text-sm font-semibold text-white hover:bg-slate-800">Open</button>
      <span className="pb-2.5 text-xs text-slate-500">The demo profile prints its id: <code>python -m delivery.seed --reset</code></span>
    </form>
  );
}
