import { notFound } from "next/navigation";
import MatchRoute from "@/components/app/MatchRoute";

export default async function MatchPage(props: PageProps<"/matches/[id]">) {
  const { id } = await props.params;
  if (!/^\d+$/.test(id)) notFound();
  return <MatchRoute key={id} matchId={Number(id)} />;
}
