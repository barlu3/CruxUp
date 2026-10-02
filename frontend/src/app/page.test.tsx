import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Home from "./page";

describe("Home page", () => {
  it("renders the CruxUp heading", () => {
    render(<Home />);
    expect(
      screen.getByRole("heading", { level: 1, name: "CruxUp" }),
    ).toBeInTheDocument();
  });

  it("links to the survey", () => {
    render(<Home />);
    expect(
      screen.getByRole("link", { name: /start the questionnaire/i }),
    ).toHaveAttribute("href", "/survey");
  });
});
