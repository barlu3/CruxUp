import Link from "next/link";

export default function Home() {
  return (
    <main className="mx-auto max-w-2xl p-8">
      <h1 className="text-3xl font-bold">CruxUp</h1>
      <p className="mt-4">
        CruxUp recommends climbing shoes matched on fit, style and budget.
      </p>
      <Link href="/survey" className="mt-6 inline-block underline">
        Start the questionnaire
      </Link>
    </main>
  );
}
