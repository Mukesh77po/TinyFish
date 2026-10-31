"use client";

import { useEffect } from "react";
import { useShell } from "./ProfileShell";

/** Attach to a sweep started elsewhere (the ?sweep= link). */
export default function FollowSweep({ sweepId }: { sweepId: string }) {
  const { follow } = useShell();
  useEffect(() => { follow(sweepId); }, [follow, sweepId]);
  return null;
}
