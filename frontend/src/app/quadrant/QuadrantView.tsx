"use client";

import { useEffect, useId, useState } from "react";

import { QuadrantChart } from "../components/QuadrantChart";
import { QuadrantTable } from "../components/QuadrantTable";
import { ApiError, getQuadrant } from "../lib/api";
import type { QuadrantShoe } from "../lib/types";

type ViewState =
  | { status: "loading" }
  | { status: "ready"; shoes: QuadrantShoe[] }
  | { status: "failed"; message: string };

export function QuadrantView() {
  const chartHeadingId = useId();
  const tableHeadingId = useId();
  const [state, setState] = useState<ViewState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let isCurrent = true;
    getQuadrant().then(
      (shoes) => {
        if (isCurrent) setState({ status: "ready", shoes });
      },
      (error: unknown) => {
        if (!isCurrent) return;
        setState({
          status: "failed",
          message: error instanceof ApiError ? error.message : "Something went wrong. Please try again.",
        });
      },
    );
    return () => {
      isCurrent = false;
    };
  }, [attempt]);

  function handleRetry() {
    setState({ status: "loading" });
    setAttempt((previous) => previous + 1);
  }

  return (
    <div className="mt-8 flex flex-col gap-8">
      {/* Mounted throughout so assistive tech keeps observing the live region. */}
      <p role="status" className="text-muted">
        {state.status === "loading" && "Loading shoes…"}
      </p>
      {state.status === "failed" && (
        <div role="alert" className="flex flex-col items-start gap-3 rounded-control border border-danger p-3 text-danger">
          <p>{state.message}</p>
          <button
            type="button"
            onClick={handleRetry}
            className="min-h-11 rounded-control bg-accent px-6 font-medium text-accent-foreground"
          >
            Try again
          </button>
        </div>
      )}
      {state.status === "ready" && (
        <>
          <section aria-labelledby={chartHeadingId} className="flex flex-col gap-3">
            <h2 id={chartHeadingId} className="text-xl font-semibold">Quadrant chart</h2>
            {/* Wider than /results: ~30 shoes need the room to keep clusters apart. */}
            <div className="mx-auto w-full max-w-xl">
              <QuadrantChart shoes={state.shoes} />
            </div>
          </section>
          <section aria-labelledby={tableHeadingId} className="flex flex-col gap-3">
            <h2 id={tableHeadingId} className="text-xl font-semibold">All shoes by quadrant</h2>
            <QuadrantTable shoes={state.shoes} />
          </section>
        </>
      )}
    </div>
  );
}
