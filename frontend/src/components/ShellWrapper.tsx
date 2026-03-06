"use client";

import { usePathname } from "next/navigation";
import Shell from "./Shell";

const SHELL_EXCLUDED = ["/login"];

export default function ShellWrapper({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();

  if (SHELL_EXCLUDED.some((p) => pathname.startsWith(p))) {
    return <>{children}</>;
  }

  return <Shell>{children}</Shell>;
}
