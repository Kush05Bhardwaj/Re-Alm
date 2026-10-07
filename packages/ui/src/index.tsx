import type { PropsWithChildren } from "react";

export function Panel({ children }: PropsWithChildren) {
  return <section className="rounded-xl border border-zinc-700 bg-zinc-900 p-4">{children}</section>;
}
