import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SurveyPage, { metadata } from "./page";

afterEach(() => vi.unstubAllGlobals());

describe("Survey page", () => {
  it("has the questionnaire title and a single h1", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    render(<SurveyPage />);
    expect(metadata.title).toBe("Questionnaire | CruxUp");
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(screen.getByText(/every question is optional/i)).toBeInTheDocument();
  });
});
