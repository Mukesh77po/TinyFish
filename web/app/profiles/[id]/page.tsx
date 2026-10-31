import FollowSweep from "@/components/app/FollowSweep";
import LiveMatches from "@/components/app/LiveMatches";

export default async function LiveMatchesPage(props: PageProps<"/profiles/[id]">) {
  const { sweep } = await props.searchParams;
  // ?sweep=<id> follows a sweep that is already running (e.g. a second screen during the demo).
  const follow = typeof sweep === "string" && /^[0-9a-f-]{36}$/i.test(sweep) ? sweep : undefined;
  return (
    <>
      {follow && <FollowSweep sweepId={follow} />}
      <LiveMatches />
    </>
  );
}
