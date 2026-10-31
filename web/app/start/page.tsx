import OpenProfile from "@/components/OpenProfile";
import ProfileForm from "@/components/ProfileForm";
import { SiteFooter, SiteHeader } from "@/components/site/SiteChrome";

export default function Start() {
  return (
    <>
      <SiteHeader />
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-4 py-10 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-2">
          <p className="text-xs font-bold uppercase tracking-wider text-amber-700">Step 1 of 1</p>
          <h1 className="text-3xl font-bold text-slate-900 sm:text-4xl">Profile once. Agents do the hunting.</h1>
          <p className="max-w-3xl text-slate-600">
            TinyFish agents sweep GeM, CPPP and Haryana e-procurement for these products, read each bid&apos;s eligibility
            rules and tell you which tenders you qualify for, with the exact clause behind every verdict.
          </p>
        </div>
        <ProfileForm />
        <OpenProfile />
      </main>
      <SiteFooter cta={false} />
    </>
  );
}
