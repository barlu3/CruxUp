import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Recommendation, RecommendResponse } from "../lib/types";

import { ResultsView } from "./ResultsView";

const fetchMock = vi.fn();
const TOKEN = "tok-123";
const TOKEN_KEY = "cruxup.surveyToken";

function makeResult(rank: number, overrides: Partial<Recommendation> = {}): Recommendation {
  return {
    id: `s${rank}`,
    brand: "Brand",
    model: `Model${rank}`,
    version: "",
    gender: "mens",
    x: 0.1 * rank,
    y: 0.2,
    prior_source: "corpus",
    is_anchor: false,
    quadrant: "Q1",
    msrp_usd: 150,
    price_unknown: false,
    fit_score: 0.8,
    style_score: 0.6,
    budget_score: 1,
    total_score: 0.9 - rank * 0.1,
    confidence: 0.9,
    confidence_label: "high",
    rank,
    warnings: [],
    ...overrides,
  };
}

function makeRanking(overrides: Partial<RecommendResponse> = {}): RecommendResponse {
  return {
    scorer_version: "v1",
    target: { x: 0.5, y: 0.5 },
    terms: { fit: true, style: true, budget: true },
    gated_out: { over_budget: 0, size_unavailable: 0, unplaced: 0 },
    warnings: [],
    results: [1, 2, 3, 4].map((rank) => makeResult(rank)),
    ...overrides,
  };
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

function renderWithToken() {
  sessionStorage.setItem(TOKEN_KEY, TOKEN);
  return render(<ResultsView />);
}

function rankedList() {
  return within(screen.getByRole("region", { name: "Ranked shoes" })).getByRole("list");
}

beforeEach(() => {
  sessionStorage.clear();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("ResultsView", () => {
  it("links to the survey when no token is stored", () => {
    render(<ResultsView />);
    expect(screen.getByRole("link", { name: /survey/i })).toHaveAttribute("href", "/survey");
  });

  it("says the survey has not been taken when no token is stored", () => {
    render(<ResultsView />);
    expect(screen.getByText("You haven't taken the survey yet.")).toBeInTheDocument();
  });

  it("shows a loading status while the request is pending", () => {
    fetchMock.mockReturnValue(new Promise(() => {}));
    renderWithToken();
    expect(screen.getByRole("status")).toHaveTextContent("Loading your results…");
  });

  it("renders one list item per result", async () => {
    fetchMock.mockResolvedValue(jsonResponse(makeRanking()));
    renderWithToken();
    await screen.findByRole("region", { name: "Ranked shoes" });
    expect(within(rankedList()).getAllByRole("listitem")).toHaveLength(4);
  });

  it("lists the rank-1 shoe first", async () => {
    fetchMock.mockResolvedValue(jsonResponse(makeRanking()));
    renderWithToken();
    await screen.findByRole("region", { name: "Ranked shoes" });
    expect(within(rankedList()).getAllByRole("listitem")[0]).toHaveTextContent("Brand Model1 (men's)");
  });

  it("labels the target on the chart", async () => {
    fetchMock.mockResolvedValue(jsonResponse(makeRanking()));
    renderWithToken();
    expect(await screen.findByRole("img", { name: "Your target" })).toBeInTheDocument();
  });

  it("marks the rank-1 point as highlighted", async () => {
    fetchMock.mockResolvedValue(jsonResponse(makeRanking()));
    renderWithToken();
    expect(await screen.findByRole("img", { name: /^Brand Model1 \(men's\)\..*Highlighted\./ })).toBeInTheDocument();
  });

  it("does not mark the rank-4 point as highlighted", async () => {
    fetchMock.mockResolvedValue(jsonResponse(makeRanking()));
    renderWithToken();
    expect(await screen.findByRole("img", { name: /^Brand Model4 \(men's\)\./ })).not.toHaveAccessibleName(/Highlighted/);
  });

  it("omits the target from the chart when the ranking has none", async () => {
    fetchMock.mockResolvedValue(jsonResponse(makeRanking({ target: null })));
    renderWithToken();
    await screen.findByRole("region", { name: "Ranked shoes" });
    expect(screen.queryByRole("img", { name: "Your target" })).not.toBeInTheDocument();
  });

  it("renders survey warnings under About these results", async () => {
    fetchMock.mockResolvedValue(jsonResponse(makeRanking({ warnings: ["no_target"] })));
    renderWithToken();
    const about = await screen.findByRole("region", { name: "About these results" });
    expect(about).toHaveTextContent("You didn't choose a discipline, so there's no style target.");
  });

  it("renders gated-out sentences", async () => {
    const gatedOut = { over_budget: 2, size_unavailable: 0, unplaced: 0 };
    fetchMock.mockResolvedValue(jsonResponse(makeRanking({ gated_out: gatedOut })));
    renderWithToken();
    expect(await screen.findByText("2 shoes priced over your budget were left out.")).toBeInTheDocument();
  });

  it("omits the unknown-price note when the survey set no budget", async () => {
    const results = [makeResult(1, { price_unknown: true, msrp_usd: null }), makeResult(2)];
    fetchMock.mockResolvedValue(
      jsonResponse(makeRanking({ results, terms: { fit: true, style: true, budget: false } })),
    );
    renderWithToken();
    await screen.findByRole("region", { name: "Ranked shoes" });
    expect(screen.queryByText(/no known price/)).not.toBeInTheDocument();
  });

  it("counts shoes with an unknown price", async () => {
    const results = [makeResult(1, { price_unknown: true, msrp_usd: null }), makeResult(2)];
    fetchMock.mockResolvedValue(jsonResponse(makeRanking({ results })));
    renderWithToken();
    expect(
      await screen.findByText(/^1 shoe has no known price\./),
    ).toBeInTheDocument();
  });

  it("explains what low confidence means", async () => {
    fetchMock.mockResolvedValue(jsonResponse(makeRanking()));
    renderWithToken();
    const about = await screen.findByRole("region", { name: "About these results" });
    expect(about).toHaveTextContent("Low confidence");
  });

  it("announces the number of ranked shoes", async () => {
    fetchMock.mockResolvedValue(jsonResponse(makeRanking()));
    renderWithToken();
    await screen.findByRole("region", { name: "Ranked shoes" });
    expect(screen.getByRole("status")).toHaveTextContent("4 shoes ranked.");
  });

  it("announces a single ranked shoe in the singular", async () => {
    fetchMock.mockResolvedValue(jsonResponse(makeRanking({ results: [makeResult(1)] })));
    renderWithToken();
    await screen.findByRole("region", { name: "Ranked shoes" });
    expect(screen.getByRole("status")).toHaveTextContent("1 shoe ranked.");
  });

  it("keeps the token stored after a 200", async () => {
    fetchMock.mockResolvedValue(jsonResponse(makeRanking()));
    renderWithToken();
    await screen.findByRole("region", { name: "Ranked shoes" });
    expect(sessionStorage.getItem(TOKEN_KEY)).toBe(TOKEN);
  });

  it("shows an empty-state message with the gated-out sentences when nothing ranks", async () => {
    const gatedOut = { over_budget: 3, size_unavailable: 0, unplaced: 0 };
    fetchMock.mockResolvedValue(jsonResponse(makeRanking({ results: [], gated_out: gatedOut })));
    renderWithToken();
    expect(await screen.findByText(/3 shoes priced over your budget were left out\./)).toBeInTheDocument();
  });

  it("says no shoes matched when nothing ranks", async () => {
    fetchMock.mockResolvedValue(jsonResponse(makeRanking({ results: [] })));
    renderWithToken();
    expect(await screen.findByText(/No shoes matched/)).toBeInTheDocument();
  });

  it("renders no chart when nothing ranks", async () => {
    fetchMock.mockResolvedValue(jsonResponse(makeRanking({ results: [] })));
    renderWithToken();
    await screen.findByText(/No shoes matched/);
    expect(screen.queryByRole("group")).not.toBeInTheDocument();
  });

  it("renders no ranked list when nothing ranks", async () => {
    fetchMock.mockResolvedValue(jsonResponse(makeRanking({ results: [] })));
    renderWithToken();
    await screen.findByText(/No shoes matched/);
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });

  it("says the survey was not found on a 404", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ errors: ["x"] }, 404));
    renderWithToken();
    expect(await screen.findByText("We couldn't find your survey.")).toBeInTheDocument();
  });

  it("removes the stored token on a 404", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ errors: ["x"] }, 404));
    renderWithToken();
    await screen.findByText("We couldn't find your survey.");
    expect(sessionStorage.getItem(TOKEN_KEY)).toBeNull();
  });

  it("links back to the survey after a 404", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ errors: ["x"] }, 404));
    renderWithToken();
    expect(await screen.findByRole("link", { name: "Take the survey again" })).toHaveAttribute("href", "/survey");
  });

  it("says the survey was not found on a 422", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ errors: ["x"] }, 422));
    renderWithToken();
    expect(await screen.findByText("We couldn't find your survey.")).toBeInTheDocument();
  });

  it("shows a fixed message in an alert on 502", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ errors: ["Backend is down"] }, 502));
    renderWithToken();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "We couldn't load your results. Please try again.",
    );
  });

  it("never shows upstream text in the failure alert", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ errors: ["Backend is down"] }, 502));
    renderWithToken();
    expect(await screen.findByRole("alert")).not.toHaveTextContent("Backend is down");
  });

  it("shows the failure alert when the response is malformed", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ...makeRanking(), results: [makeResult(2)] }));
    renderWithToken();
    expect(await screen.findByRole("alert")).toHaveTextContent("We couldn't load your results.");
  });

  it("renders the list after a failure followed by Try again", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ errors: ["Backend is down"] }, 502))
      .mockResolvedValueOnce(jsonResponse(makeRanking()));
    renderWithToken();
    fireEvent.click(await screen.findByRole("button", { name: "Try again" }));
    await screen.findByRole("region", { name: "Ranked shoes" });
    expect(within(rankedList()).getAllByRole("listitem")).toHaveLength(4);
  });

  it("announces the not-found message in the status region", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ errors: ["x"] }, 404));
    renderWithToken();
    await screen.findByRole("link", { name: "Take the survey again" });
    expect(screen.getByRole("status")).toHaveTextContent("We couldn't find your survey.");
  });

  it("moves focus to the not-found message", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ errors: ["x"] }, 404));
    renderWithToken();
    await screen.findByRole("link", { name: "Take the survey again" });
    expect(document.activeElement).toBe(screen.getByRole("status"));
  });

  it("moves focus to the alert on failure", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ errors: ["Backend is down"] }, 502));
    renderWithToken();
    await screen.findByRole("alert");
    await waitFor(() => expect(screen.getByRole("alert")).toHaveFocus());
  });

  it("moves focus to the status region when Try again is clicked", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ errors: ["Backend is down"] }, 502))
      .mockReturnValueOnce(new Promise(() => {}));
    renderWithToken();
    const retry = await screen.findByRole("button", { name: "Try again" });
    await waitFor(() => expect(screen.getByRole("alert")).toHaveFocus());
    fireEvent.click(retry);
    expect(document.activeElement).toBe(screen.getByRole("status"));
  });

  it("links back to the survey from the empty state", async () => {
    fetchMock.mockResolvedValue(jsonResponse(makeRanking({ results: [] })));
    renderWithToken();
    expect(await screen.findByRole("link", { name: "Adjust your survey" })).toHaveAttribute("href", "/survey");
  });

  it("explains that left-out shoes are not charted", async () => {
    fetchMock.mockResolvedValue(jsonResponse(makeRanking()));
    renderWithToken();
    expect(
      await screen.findByText("Your top 3 are highlighted. Only ranked shoes appear; shoes that were left out are not shown."),
    ).toBeInTheDocument();
  });

  it("names only the shoes that exist when there are fewer than three", async () => {
    fetchMock.mockResolvedValue(jsonResponse(makeRanking({ results: [makeResult(1), makeResult(2)] })));
    renderWithToken();
    expect(await screen.findByText(/^Your top 2 are highlighted\./)).toBeInTheDocument();
  });

  it("uses the singular when there is one ranked shoe", async () => {
    fetchMock.mockResolvedValue(jsonResponse(makeRanking({ results: [makeResult(1)] })));
    renderWithToken();
    expect(await screen.findByText(/^Your top shoe is highlighted\./)).toBeInTheDocument();
  });

  it("sends the token only in the request body", async () => {
    fetchMock.mockResolvedValue(jsonResponse(makeRanking()));
    renderWithToken();
    await screen.findByRole("region", { name: "Ranked shoes" });
    expect(fetchMock).toHaveBeenCalledWith("/api/recommend", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ survey_token: TOKEN }),
    }));
  });

  it("logs no console error when unmounted before the request resolves", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    let resolveFetch: (response: Response) => void = () => {};
    fetchMock.mockReturnValue(new Promise<Response>((resolve) => (resolveFetch = resolve)));
    const { unmount } = renderWithToken();
    unmount();
    resolveFetch(jsonResponse(makeRanking()));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(consoleError).not.toHaveBeenCalled();
  });
});
