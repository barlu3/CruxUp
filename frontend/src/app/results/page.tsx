import type { Metadata } from "next";

import { ResultsView } from "./ResultsView";

export const metadata: Metadata = {
  title: "Your results | CruxUp",
};

export default function ResultsPage() {
  return (
    <main className="mx-auto max-w-4xl p-4 sm:p-8">
      <h1 className="text-3xl font-bold">Your results</h1>
      <p className="mt-4 text-muted">
        Suggested starting points, not a guaranteed fit. Shoe positions are estimates, and the fit rules have not yet been checked by climbers. Try shoes on before you buy.
      </p>
      <ResultsView />
    </main>
  );
}
