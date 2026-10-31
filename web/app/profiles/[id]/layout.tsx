import { notFound } from "next/navigation";
import ProfileShell from "@/components/app/ProfileShell";

export default async function ProfileLayout(props: LayoutProps<"/profiles/[id]">) {
  const { id } = await props.params;
  if (!/^\d+$/.test(id)) notFound();
  return <ProfileShell key={id} profileId={Number(id)}>{props.children}</ProfileShell>;
}
