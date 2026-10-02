import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import shoes from "../../../e2e/fixtures/shoes.json";
import { SurveyForm } from "./SurveyForm";

type FetchMock = ReturnType<typeof vi.fn>;

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });

let fetchMock: FetchMock;

function installFetch(opts: {
  shoesResponse?: () => Promise<Response> | Response;
  surveyResponse?: () => Promise<Response> | Response;
} = {}) {
  fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/shoes") {
      return opts.shoesResponse ? opts.shoesResponse() : json(200, shoes);
    }
    if (url === "/api/survey") {
      return opts.surveyResponse
        ? opts.surveyResponse()
        : json(201, { survey_token: "tok" });
    }
    throw new Error(`unexpected fetch ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
}

const surveyCalls = () =>
  fetchMock.mock.calls.filter((c) => String(c[0]) === "/api/survey");

beforeEach(() => installFetch());
afterEach(() => vi.unstubAllGlobals());

async function renderReady() {
  const user = userEvent.setup();
  render(<SurveyForm />);
  await waitFor(() =>
    expect(screen.getByLabelText("Shoes that fit you well")).toBeEnabled(),
  );
  return user;
}

const ORDER = [
  "Foot width",
  "Instep",
  "Toe shape",
  "Arch",
  "Heel fit",
  "Street size (US)",
  "Discipline",
  "Terrain",
  "Level",
  "Budget cap (US dollars)",
  "Shoes that fit you well",
  "Shoes that fit you badly",
];

describe("SurveyForm", () => {
  it("labels every control", async () => {
    await renderReady();
    for (const name of ORDER) {
      expect(screen.getByLabelText(name), name).toBeInTheDocument();
    }
    const selects = screen.getAllByRole("combobox").filter((e) => e.tagName === "SELECT");
    expect(selects).toHaveLength(8);
    expect(screen.getByLabelText("Street size (US)")).toHaveAttribute("type", "number");
    expect(screen.getByLabelText("Budget cap (US dollars)")).toHaveAttribute("type", "number");
    expect(screen.getAllByRole("group").length).toBeGreaterThanOrEqual(4);
  });

  it("offers a blank 'Not sure' first and the exact backend values", async () => {
    await renderReady();
    const toe = screen.getByLabelText("Toe shape") as HTMLSelectElement;
    expect([...toe.options].map((o) => o.value)).toEqual(["", "egyptian", "greek", "roman"]);
    expect(toe.options[0]).toHaveTextContent("Not sure");
    expect(toe.options[1]).toHaveTextContent("Egyptian — big toe longest");
    const disc = screen.getByLabelText("Discipline") as HTMLSelectElement;
    expect([...disc.options].map((o) => o.value)).toEqual(["", "boulder", "sport", "trad", "gym"]);
    expect(disc.options[1]).toHaveTextContent("Bouldering");
  });

  it("mirrors the server number rules on the inputs", async () => {
    await renderReady();
    const street = screen.getByLabelText("Street size (US)");
    expect(street).toHaveAttribute("min", "0.1");
    expect(street).toHaveAttribute("max", "20");
    expect(street).toHaveAttribute("step", "0.1");
    const budget = screen.getByLabelText("Budget cap (US dollars)");
    expect(budget).toHaveAttribute("min", "0.01");
    expect(budget).toHaveAttribute("max", "99999.99");
    expect(budget).toHaveAttribute("step", "0.01");
  });

  it("reaches every control by Tab in DOM order, including submit", async () => {
    const user = await renderReady();
    const expected = [
      ...ORDER.map((n) => screen.getByLabelText(n)),
      screen.getByRole("button", { name: "Submit answers" }),
    ];
    document.body.focus();
    for (const el of expected) {
      await user.tab();
      expect(el).toHaveFocus();
    }
  });

  it("finds the size and remove controls of a selected anchor", async () => {
    const user = await renderReady();
    await user.type(screen.getByLabelText("Shoes that fit you well"), "drago");
    await user.keyboard("{ArrowDown}{Enter}");
    expect(screen.getByLabelText("Size (optional) for Scarpa Drago (unisex)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove Scarpa Drago (unisex)" })).toBeInTheDocument();
  });

  it("does not offer a shoe picked as good in the bad picker", async () => {
    const user = await renderReady();
    await user.type(screen.getByLabelText("Shoes that fit you well"), "drago");
    await user.keyboard("{ArrowDown}{Enter}");
    await user.type(screen.getByLabelText("Shoes that fit you badly"), "drago");
    expect(screen.queryByRole("listbox")).toBeNull();
    // Not vacuous: the bad picker says why nothing is offered.
    const regions = screen.getAllByRole("status");
    expect(regions[1]).toHaveTextContent("No matching shoes. Shoes you already chose are not shown.");
  });

  it("submits an anchors-only answer (all-NULL fit profile) and shows the confirmation", async () => {
    const user = await renderReady();
    await user.type(screen.getByLabelText("Shoes that fit you well"), "instinct");
    await user.keyboard("{ArrowDown}{ArrowDown}{Enter}");
    await user.tab(); // size
    await user.tab(); // remove
    await user.tab(); // bad picker
    await user.tab(); // submit
    expect(screen.getByRole("button", { name: "Submit answers" })).toHaveFocus();
    await user.keyboard("{Enter}");

    await waitFor(() => expect(screen.getByRole("status")).toBeInTheDocument());
    expect(surveyCalls()).toHaveLength(1);
    const [url, init] = surveyCalls()[0] as [string, RequestInit];
    expect(url).toBe("/api/survey");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      known_good_shoes: [
        { brand: "Scarpa", model: "Instinct", version: "VSR", gender: "unisex" },
      ],
    });
    const status = screen.getByRole("status");
    const heading = screen.getByRole("heading", { name: /thank/i });
    expect(status).toContainElement(heading);
    expect(heading).toHaveFocus();
    expect(screen.queryByText("tok")).toBeNull();
    expect(screen.queryByRole("button", { name: "Submit answers" })).toBeNull();
  });

  it("submits an empty form as {}", async () => {
    const user = await renderReady();
    await user.click(screen.getByRole("button", { name: "Submit answers" }));
    await waitFor(() => expect(screen.getByRole("status")).toBeInTheDocument());
    expect(JSON.parse((surveyCalls()[0][1] as RequestInit).body as string)).toEqual({});
  });

  it("sends selects and numbers with the right types", async () => {
    const user = await renderReady();
    await user.selectOptions(screen.getByLabelText("Foot width"), "wide");
    await user.selectOptions(screen.getByLabelText("Level"), "elite");
    await user.type(screen.getByLabelText("Street size (US)"), "9.5");
    await user.type(screen.getByLabelText("Budget cap (US dollars)"), "120.5");
    await user.click(screen.getByRole("button", { name: "Submit answers" }));
    await waitFor(() => expect(surveyCalls()).toHaveLength(1));
    expect(JSON.parse((surveyCalls()[0][1] as RequestInit).body as string)).toEqual({
      foot_width: "wide",
      level: "elite",
      street_size: 9.5,
      budget_cap_usd: 120.5,
    });
  });

  it("renders 422 errors as literal text and keeps the answers", async () => {
    installFetch({
      surveyResponse: () =>
        json(422, { errors: ["brand '<b>x</b>' is unknown", "second problem"] }),
    });
    const user = await renderReady();
    await user.selectOptions(screen.getByLabelText("Arch"), "high");
    await user.click(screen.getByRole("button", { name: "Submit answers" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("brand '<b>x</b>' is unknown");
    expect(alert.querySelector("b")).toBeNull();
    expect(screen.getAllByRole("listitem").map((l) => l.textContent)).toEqual(
      expect.arrayContaining(["brand '<b>x</b>' is unknown", "second problem"]),
    );
    expect(screen.getByLabelText("Arch")).toHaveValue("high");
    expect(screen.getByRole("button", { name: "Submit answers" })).toBeEnabled();
  });

  it("shows one generic alert on a network failure", async () => {
    installFetch({
      surveyResponse: () => {
        throw new TypeError("fetch failed");
      },
    });
    const user = await renderReady();
    await user.click(screen.getByRole("button", { name: "Submit answers" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/something went wrong/i);
    expect(screen.queryByRole("heading", { name: /thank/i })).toBeNull();
  });

  it("shows the generic alert for a non-201, non-422 reply", async () => {
    installFetch({ surveyResponse: () => json(503, { detail: "database unavailable" }) });
    const user = await renderReady();
    await user.click(screen.getByRole("button", { name: "Submit answers" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/something went wrong/i);
    expect(alert).not.toHaveTextContent("database unavailable");
  });

  it("marks submit busy (aria-disabled, not disabled) while pending and ignores a second submit", async () => {
    let release: (r: Response) => void = () => {};
    installFetch({
      surveyResponse: () => new Promise<Response>((res) => (release = res)),
    });
    const user = await renderReady();
    const submit = screen.getByRole("button", { name: "Submit answers" });
    expect(submit).toHaveAttribute("aria-disabled", "false");
    await user.click(submit);
    await waitFor(() => expect(submit).toHaveAttribute("aria-disabled", "true"));
    expect(submit).toBeEnabled();
    await user.click(submit);
    await user.keyboard("{Enter}");
    expect(surveyCalls()).toHaveLength(1);
    release(json(201, { survey_token: "t" }));
    await waitFor(() => expect(screen.getByRole("status")).toBeInTheDocument());
    expect(surveyCalls()).toHaveLength(1);
  });

  it("shows Sending… while pending and returns to normal after a 422", async () => {
    let release: (r: Response) => void = () => {};
    installFetch({
      surveyResponse: () => new Promise<Response>((res) => (release = res)),
    });
    const user = await renderReady();
    const submit = screen.getByRole("button", { name: "Submit answers" });
    await user.click(submit);
    await waitFor(() => expect(submit).toHaveTextContent("Sending…"));
    expect(submit).toHaveAttribute("aria-disabled", "true");
    release(json(422, { errors: ["bad"] }));
    await screen.findByRole("alert");
    expect(submit).toHaveAttribute("aria-disabled", "false");
    expect(submit).toHaveTextContent("Submit answers");
  });

  it("moves focus to the alert after a 422", async () => {
    installFetch({ surveyResponse: () => json(422, { errors: ["bad"] }) });
    const user = await renderReady();
    await user.click(screen.getByRole("button", { name: "Submit answers" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveAttribute("tabindex", "-1");
    await waitFor(() => expect(alert).toHaveFocus());
    expect(alert).toHaveTextContent("Please check your answers.");
  });

  it("moves focus to a generic alert with its own wording, without the 422 heading", async () => {
    installFetch({ surveyResponse: () => json(500, { detail: "x" }) });
    const user = await renderReady();
    await user.click(screen.getByRole("button", { name: "Submit answers" }));
    const alert = await screen.findByRole("alert");
    await waitFor(() => expect(alert).toHaveFocus());
    expect(alert).toHaveTextContent(/something went wrong/i);
    expect(alert).not.toHaveTextContent("Please check your answers.");
  });

  it("treats a malformed catalogue row as a catalogue error", async () => {
    installFetch({
      shoesResponse: () =>
        json(200, [...shoes.slice(0, 2), { id: 5, brand: "x", model: "y", version: "", gender: "mens" }]),
    });
    render(<SurveyForm />);
    await waitFor(() =>
      expect(screen.getByLabelText("Shoes that fit you well")).toBeDisabled(),
    );
    for (const region of await screen.findAllByRole("status")) {
      await waitFor(() => expect(region).toHaveTextContent(/shoe list could not be loaded/i));
    }
  });

  it("still submits a fit-only answer when the catalogue fails to load", async () => {
    installFetch({ shoesResponse: () => json(503, { detail: "database unavailable" }) });
    const user = userEvent.setup();
    render(<SurveyForm />);
    await waitFor(() => expect(screen.getAllByRole("status")).toHaveLength(2));
    for (const region of screen.getAllByRole("status")) {
      await waitFor(() => expect(region).toHaveTextContent(/shoe list could not be loaded/i));
    }
    expect(screen.getByLabelText("Shoes that fit you well")).toBeDisabled();
    await user.selectOptions(screen.getByLabelText("Instep"), "low");
    await user.click(screen.getByRole("button", { name: "Submit answers" }));
    await waitFor(() => expect(screen.getByRole("status")).toBeInTheDocument());
    expect(JSON.parse((surveyCalls()[0][1] as RequestInit).body as string)).toEqual({
      instep: "low",
    });
  });

  it("shows a loading state until the catalogue arrives", async () => {
    let release: (r: Response) => void = () => {};
    installFetch({ shoesResponse: () => new Promise<Response>((res) => (release = res)) });
    render(<SurveyForm />);
    expect(screen.getByLabelText("Shoes that fit you well")).toBeDisabled();
    for (const region of screen.getAllByRole("status")) {
      expect(region).toHaveTextContent("Loading shoes…");
    }
    release(json(200, shoes));
    await waitFor(() => expect(screen.getByLabelText("Shoes that fit you well")).toBeEnabled());
  });

  it("aborts the catalogue request when unmounted", async () => {
    let release: (r: Response) => void = () => {};
    installFetch({ shoesResponse: () => new Promise<Response>((res) => (release = res)) });
    const { unmount } = render(<SurveyForm />);
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.signal?.aborted).toBe(false);
    unmount();
    expect(init.signal?.aborted).toBe(true);
    release(json(200, shoes));
  });

  it("offers Try again after a catalogue failure and enables the pickers on success", async () => {
    let calls = 0;
    installFetch({
      shoesResponse: () => (++calls === 1 ? json(503, { detail: "x" }) : json(200, shoes)),
    });
    const user = userEvent.setup();
    render(<SurveyForm />);
    const retries = await screen.findAllByRole("button", { name: /try again/i });
    expect(retries.length).toBeGreaterThanOrEqual(1);
    await user.click(retries[0]);
    await waitFor(() => expect(screen.getByLabelText("Shoes that fit you well")).toBeEnabled());
    expect(screen.queryByRole("button", { name: /try again/i })).toBeNull();
    expect(calls).toBe(2);
  });

  describe("size errors", () => {
    const charset = (where: string) =>
      `${where}: 'size' contains [','] -- it records a brand size, not free text (D4: no direct identifiers)`;

    async function submitWithSize(errors: string[]) {
      installFetch({ surveyResponse: () => json(422, { errors }) });
      const user = await renderReady();
      await user.type(screen.getByLabelText("Shoes that fit you well"), "instinct");
      await user.keyboard("{ArrowDown}{ArrowDown}{Enter}");
      const size = screen.getByLabelText("Size (optional) for Scarpa Instinct VSR (unisex)");
      await user.type(size, "4,1");
      await user.click(screen.getByRole("button", { name: "Submit answers" }));
      const alert = await screen.findByRole("alert");
      return { user, alert, size };
    }

    it("translates a charset error into plain language naming the shoe", async () => {
      const { alert } = await submitWithSize([charset("known_good_shoes[0]")]);
      expect(alert).toHaveTextContent("Please check your answers.");
      expect(alert).toHaveTextContent(
        "Size for Scarpa Instinct VSR (unisex): use only letters, numbers, spaces and . / + - (for example 41 or 8.5).",
      );
      expect(alert.textContent).not.toMatch(/known_|D4/);
      expect(alert.querySelector("details")).toBeNull();
    });

    it("flags the size input, links the error, and clears the flag on edit", async () => {
      const { user, alert, size } = await submitWithSize([charset("known_good_shoes[0]")]);
      expect(size).toHaveAttribute("aria-invalid", "true");
      const errorId = size.getAttribute("aria-describedby")!.split(" ").pop()!;
      expect(alert.querySelector(`#${CSS.escape(errorId)}`)).not.toBeNull();
      await user.type(size, "x");
      expect(size).not.toHaveAttribute("aria-invalid");
      expect(size.getAttribute("aria-describedby")).not.toContain(errorId);
    });

    it("moves focus to the field from the error link", async () => {
      const { user, alert, size } = await submitWithSize([charset("known_good_shoes[0]")]);
      await user.click(within(alert).getByRole("link", { name: /Size for Scarpa Instinct VSR/ }));
      expect(size).toHaveFocus();
    });

    it("reaches the error link by keyboard after the alert", async () => {
      const { user, alert } = await submitWithSize([charset("known_good_shoes[0]")]);
      await waitFor(() => expect(alert).toHaveFocus());
      await user.tab();
      expect(within(alert).getByRole("link")).toHaveFocus();
    });

    it("translates the length error", async () => {
      const { alert } = await submitWithSize([
        "known_good_shoes[0]: 'size' is 70 characters, maximum 64",
      ]);
      expect(alert).toHaveTextContent(
        "Size for Scarpa Instinct VSR (unisex): use 64 characters or fewer.",
      );
    });

    it("falls back to plain wording with raw text in details for unknown messages", async () => {
      const { alert } = await submitWithSize(["brand '<b>x</b>' is unknown"]);
      expect(alert).toHaveTextContent(
        "One of your answers could not be accepted. Please check them and try again.",
      );
      const details = alert.querySelector("details")!;
      expect(details.querySelector("summary")).toHaveTextContent("Technical details");
      expect(details).toHaveTextContent("brand '<b>x</b>' is unknown");
      expect(alert.querySelector("b")).toBeNull();
      expect(alert.querySelector("a")).toBeNull();
    });
  });
});
