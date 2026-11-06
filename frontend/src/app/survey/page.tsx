import type { Metadata } from "next";

import { SurveyForm } from "./SurveyForm";

export const metadata: Metadata = {
  title: "Find your climbing shoe | CruxUp",
};

export default function SurveyPage() {
  return (
    <main className="mx-auto max-w-2xl p-8">
      <h1 className="text-3xl font-bold">Find your climbing shoe</h1>
      <p className="mt-4 text-muted">
        Tell us about your feet and how you climb. Every question is optional; the more you
        answer, the better the match.
      </p>
      <SurveyForm />
    </main>
  );
}
