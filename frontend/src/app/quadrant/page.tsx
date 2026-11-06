import type { Metadata } from "next";

import { QuadrantView } from "./QuadrantView";

export const metadata: Metadata = {
  title: "Shoe quadrant | CruxUp",
};

export default function QuadrantPage() {
  return (
    <main className="mx-auto max-w-4xl p-4 sm:p-8">
      <h1 className="text-3xl font-bold">Shoe quadrant</h1>
      <p className="mt-4 text-muted">
        Every shoe is placed on two axes: comfort to performance, and stiff to soft. Each
        shoe&apos;s position is an estimate. Today they are hand-placed or derived from specs;
        review-based placements will be marked as such.
      </p>
      <QuadrantView />
    </main>
  );
}
