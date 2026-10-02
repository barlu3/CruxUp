import type { Metadata } from "next";

import { SurveyForm } from "../components/SurveyForm";

export const metadata: Metadata = {
  title: "Questionnaire | CruxUp",
};

export default function SurveyPage() {
  return (
    <main className="mx-auto max-w-2xl p-8">
      <h1 className="text-3xl font-bold">Questionnaire</h1>
      <p className="mt-4">
        Every question is optional, and naming shoes you already know helps
        most.
      </p>
      <SurveyForm />
    </main>
  );
}
