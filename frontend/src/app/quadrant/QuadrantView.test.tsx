import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { QuadrantView } from "./QuadrantView";

const fetchMock = vi.fn();

const DRAGO = { id: "drago", brand: "Scarpa", model: "Drago", version: "", gender: "unisex", x: 0.8, y: 0.7, prior_source: "hand", is_anchor: true, quadrant: "Q4" };
const CHART_NAME = "Shoe quadrant chart: comfort to performance, stiff to soft";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("QuadrantView", () => {
  it("shows a loading status before the request resolves", () => {
    fetchMock.mockReturnValue(new Promise(() => {}));
    render(<QuadrantView />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading shoes…");
  });

  it("keeps the same status element after loading finishes", async () => {
    fetchMock.mockResolvedValue(jsonResponse([DRAGO]));
    render(<QuadrantView />);
    const status = screen.getByRole("status");
    await screen.findByRole("group", { name: CHART_NAME });
    expect(screen.getByRole("status")).toBe(status);
  });

  it("clears the loading text once loaded", async () => {
    fetchMock.mockResolvedValue(jsonResponse([DRAGO]));
    render(<QuadrantView />);
    await screen.findByRole("group", { name: CHART_NAME });
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });

  it("renders the chart after a 200", async () => {
    fetchMock.mockResolvedValue(jsonResponse([DRAGO]));
    render(<QuadrantView />);
    expect(await screen.findByRole("group", { name: CHART_NAME })).toBeInTheDocument();
  });

  it("renders the table after a 200", async () => {
    fetchMock.mockResolvedValue(jsonResponse([DRAGO]));
    render(<QuadrantView />);
    expect(await screen.findByRole("table", { name: "All shoes by quadrant" })).toBeInTheDocument();
  });

  it("heads the chart section with an h2", async () => {
    fetchMock.mockResolvedValue(jsonResponse([DRAGO]));
    render(<QuadrantView />);
    expect(await screen.findByRole("heading", { level: 2, name: "Quadrant chart" })).toBeInTheDocument();
  });

  it("heads the table section with an h2", async () => {
    fetchMock.mockResolvedValue(jsonResponse([DRAGO]));
    render(<QuadrantView />);
    expect(await screen.findByRole("heading", { level: 2, name: "All shoes by quadrant" })).toBeInTheDocument();
  });

  it("labels the chart section by its heading", async () => {
    fetchMock.mockResolvedValue(jsonResponse([DRAGO]));
    render(<QuadrantView />);
    expect(await screen.findByRole("region", { name: "Quadrant chart" })).toBeInTheDocument();
  });

  it("shows a plain-language alert when the route answers 502", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ errors: ["The quadrant service is unavailable."] }, 502));
    render(<QuadrantView />);
    expect(await screen.findByRole("alert")).toHaveTextContent("The shoe placements could not be loaded.");
  });

  it("shows the same alert for a malformed body", async () => {
    fetchMock.mockResolvedValue(jsonResponse([{ id: 1 }]));
    render(<QuadrantView />);
    expect(await screen.findByRole("alert")).toHaveTextContent("The shoe placements could not be loaded.");
  });

  it("renders the chart after a failure followed by Try again", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ errors: ["The quadrant service is unavailable."] }, 502))
      .mockResolvedValueOnce(jsonResponse([DRAGO]));
    render(<QuadrantView />);
    fireEvent.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("group", { name: CHART_NAME })).toBeInTheDocument();
  });

  it("logs no console error when unmounted before the request resolves", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    let resolveFetch: (response: Response) => void = () => {};
    fetchMock.mockReturnValue(new Promise<Response>((resolve) => (resolveFetch = resolve)));
    const { unmount } = render(<QuadrantView />);
    unmount();
    resolveFetch(jsonResponse([DRAGO]));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(consoleError).not.toHaveBeenCalled();
  });
});
