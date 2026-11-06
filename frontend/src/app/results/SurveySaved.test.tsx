import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { SurveySaved } from "./SurveySaved";

beforeEach(() => {
  sessionStorage.clear();
});

describe("SurveySaved", () => {
  it("confirms the save when a token is stored", () => {
    sessionStorage.setItem("cruxup.surveyToken", "tok");
    render(<SurveySaved />);
    expect(screen.getByText(/Survey saved/)).toBeInTheDocument();
  });

  it("says there is no survey when no token is stored", () => {
    render(<SurveySaved />);
    expect(screen.getByText("No survey yet")).toBeInTheDocument();
  });

  it("links back to the survey when no token is stored", () => {
    render(<SurveySaved />);
    expect(screen.getByRole("link", { name: /survey/i })).toHaveAttribute("href", "/survey");
  });
});
