import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ResultsPage from "./page";

beforeEach(() => {
  sessionStorage.clear();
  vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));
});

describe("Results page", () => {
  it("renders the Your results heading", () => {
    render(<ResultsPage />);
    expect(screen.getByRole("heading", { level: 1, name: "Your results" })).toBeInTheDocument();
  });

  it("shows the honesty intro", () => {
    render(<ResultsPage />);
    expect(
      screen.getByText(
        "Suggested starting points, not a guaranteed fit. Shoe positions are estimates, and the fit rules have not yet been checked by climbers. Try shoes on before you buy.",
      ),
    ).toBeInTheDocument();
  });
});
