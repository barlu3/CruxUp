import type { Metadata } from "next";

import { SurveySaved } from "./SurveySaved";

export const metadata: Metadata = {
  title: "Your results | CruxUp",
};

export default function ResultsPage() {
  return (
    <main className="mx-auto max-w-2xl p-8">
      <h1 className="text-3xl font-bold">Your results</h1>
      <SurveySaved />
    </main>
  );
}
