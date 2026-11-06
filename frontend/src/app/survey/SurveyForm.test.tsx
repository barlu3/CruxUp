import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, getShoes, submitSurvey } from "../lib/api";

import { SurveyForm } from "./SurveyForm";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

vi.mock("../lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../lib/api")>()),
  getShoes: vi.fn(),
  submitSurvey: vi.fn(),
}));

const TOKEN = "tok-secret-123";

async function renderForm() {
  render(<SurveyForm />);
  await waitFor(() => expect(getShoes).toHaveBeenCalled());
}

function chooseDiscipline(value: string) {
  fireEvent.change(screen.getByLabelText("Discipline"), { target: { value } });
}

function submit() {
  fireEvent.click(screen.getByRole("button", { name: "Find my shoes" }));
}

function findErrorBox() {
  return screen.findByRole("region", { name: "We couldn't save your survey" });
}

beforeEach(() => {
  push.mockReset();
  vi.mocked(submitSurvey).mockReset();
  sessionStorage.clear();
  vi.mocked(getShoes).mockResolvedValue([]);
  vi.mocked(submitSurvey).mockResolvedValue({ ok: true, surveyToken: TOKEN });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("SurveyForm", () => {
  it.each([
    "Foot width",
    "Instep",
    "Toe shape",
    "Arch",
    "Heel fit",
    "Street shoe size (US)",
    "Discipline",
    "Terrain",
    "Level",
    "Budget (USD)",
  ])("labels the %s field", async (label) => {
    await renderForm();
    expect(screen.getByLabelText(label)).toBeInTheDocument();
  });

  it.each(["Shoes that fit you well", "Shoes that fit you badly"])("labels the %s picker", async (name) => {
    await renderForm();
    expect(screen.getByRole("combobox", { name })).toBeInTheDocument();
  });

  it("describes the toe shape options", async () => {
    await renderForm();
    expect(screen.getByRole("option", { name: /Egyptian.*big toe longest/ })).toHaveValue("egyptian");
  });

  it("offers a prefer-not-to-say option on foot width", async () => {
    await renderForm();
    expect(screen.getByLabelText("Foot width")).toHaveValue("");
  });

  it("disables the goal radios until a discipline is chosen", async () => {
    await renderForm();
    expect(screen.getByRole("radio", { name: "Balanced" })).toBeDisabled();
  });

  it("explains why the goal is disabled", async () => {
    await renderForm();
    expect(screen.getByRole("group", { name: "Comfort or performance?" })).toHaveAccessibleDescription(
      /discipline/i,
    );
  });

  it("enables the goal radios after choosing a discipline", async () => {
    await renderForm();
    chooseDiscipline("boulder");
    expect(screen.getByRole("radio", { name: "Balanced" })).toBeEnabled();
  });

  it("unchecks the goal when the discipline is cleared", async () => {
    await renderForm();
    chooseDiscipline("boulder");
    fireEvent.click(screen.getByRole("radio", { name: "Max performance" }));
    chooseDiscipline("");
    expect(screen.getByRole("radio", { name: "Max performance" })).not.toBeChecked();
  });

  it("submits the payload built from the form", async () => {
    await renderForm();
    chooseDiscipline("boulder");
    fireEvent.click(screen.getByRole("radio", { name: "Leaning comfort" }));
    submit();
    await waitFor(() => expect(submitSurvey).toHaveBeenCalledWith({ discipline: "boulder", goal: -0.5 }));
  });

  it("renders 422 errors as text in the error box", async () => {
    vi.mocked(submitSurvey).mockResolvedValue({ ok: false, errors: ["street_size out of range"] });
    await renderForm();
    submit();
    expect(await findErrorBox()).toHaveTextContent("street_size out of range");
  });

  it("moves focus to the error box after a 422", async () => {
    vi.mocked(submitSurvey).mockResolvedValue({ ok: false, errors: ["bad"] });
    await renderForm();
    submit();
    await waitFor(async () => expect(await findErrorBox()).toHaveFocus());
  });

  it("calls submitSurvey once for two quick submits", async () => {
    vi.mocked(submitSurvey).mockReturnValue(new Promise(() => {}));
    await renderForm();
    chooseDiscipline("sport");
    const form = screen.getByRole("button", { name: "Find my shoes" }).closest("form")!;
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(vi.mocked(submitSurvey).mock.calls).toEqual([[{ discipline: "sport" }]]);
  });

  it("sends an out-of-range street size without browser validation blocking it", async () => {
    await renderForm();
    fireEvent.change(screen.getByLabelText("Street shoe size (US)"), { target: { value: "25" } });
    submit();
    await waitFor(() => expect(submitSurvey).toHaveBeenCalledWith({ street_size: 25 }));
  });

  it("renders markup in an error literally", async () => {
    vi.mocked(submitSurvey).mockResolvedValue({ ok: false, errors: ["<b>x</b>"] });
    await renderForm();
    submit();
    expect(await findErrorBox()).toHaveTextContent("<b>x</b>");
  });

  it("keeps form values after a 422", async () => {
    vi.mocked(submitSurvey).mockResolvedValue({ ok: false, errors: ["bad"] });
    await renderForm();
    chooseDiscipline("sport");
    submit();
    await findErrorBox();
    expect(screen.getByLabelText("Discipline")).toHaveValue("sport");
  });

  it("renders an ApiError message in the error box", async () => {
    vi.mocked(submitSurvey).mockRejectedValue(new ApiError("unavailable", "Service is down."));
    await renderForm();
    submit();
    expect(await findErrorBox()).toHaveTextContent("Service is down.");
  });

  it("stores the token in sessionStorage on success", async () => {
    await renderForm();
    submit();
    await waitFor(() => expect(sessionStorage.getItem("cruxup.surveyToken")).toBe(TOKEN));
  });

  it("navigates to /results on success", async () => {
    await renderForm();
    submit();
    await waitFor(() => expect(push).toHaveBeenCalledWith("/results"));
  });

  it("navigates even when sessionStorage throws", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("denied");
    });
    await renderForm();
    submit();
    await waitFor(() => expect(push).toHaveBeenCalledWith("/results"));
  });

  it("never puts the token in the pushed URL", async () => {
    await renderForm();
    submit();
    await waitFor(() => expect(push).toHaveBeenCalled());
    expect(push.mock.calls[0][0]).not.toContain(TOKEN);
  });

  it("disables the submit button while submitting", async () => {
    vi.mocked(submitSurvey).mockReturnValue(new Promise(() => {}));
    await renderForm();
    submit();
    expect(await screen.findByRole("button", { name: "Find my shoes" })).toBeDisabled();
  });

  it("marks the form busy while submitting", async () => {
    vi.mocked(submitSurvey).mockReturnValue(new Promise(() => {}));
    await renderForm();
    submit();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Find my shoes" })).toHaveAttribute("aria-busy", "true"),
    );
  });

  it("shows a polite status while shoes load", () => {
    vi.mocked(getShoes).mockReturnValue(new Promise(() => {}));
    render(<SurveyForm />);
    expect(screen.getByText(/loading shoes/i)).toBeInTheDocument();
  });

  it("shows a non-blocking message when the shoe list fails", async () => {
    vi.mocked(getShoes).mockRejectedValue(new ApiError("unavailable", "down"));
    render(<SurveyForm />);
    expect(await screen.findByText(/Couldn't load the shoe list/)).toBeInTheDocument();
  });

  it("keeps submit enabled when the shoe list fails", async () => {
    vi.mocked(getShoes).mockRejectedValue(new ApiError("unavailable", "down"));
    render(<SurveyForm />);
    await screen.findByText(/Couldn't load the shoe list/);
    expect(screen.getByRole("button", { name: "Find my shoes" })).toBeEnabled();
  });
});
