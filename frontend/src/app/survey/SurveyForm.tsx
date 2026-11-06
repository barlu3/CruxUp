"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";

import { ApiError, getShoes, submitSurvey } from "../lib/api";
import { toSurveyPayload } from "../lib/survey-payload";
import type { SurveyFormState } from "../lib/survey-payload";
import { SURVEY_TOKEN_KEY } from "../lib/survey-token";
import {
  ARCHES,
  DISCIPLINES,
  FOOT_WIDTHS,
  HEEL_FITS,
  INSTEPS,
  LEVELS,
  TERRAINS,
  TOE_SHAPES,
} from "../lib/types";
import type { Shoe } from "../lib/types";

import { AnchorPicker } from "./AnchorPicker";

type FieldKey = {
  [K in keyof SurveyFormState]: SurveyFormState[K] extends string ? K : never;
}[keyof SurveyFormState];

type Option = { value: string; label: string };

const GOAL_OPTIONS = [
  { value: -1, label: "All-day comfort" },
  { value: -0.5, label: "Leaning comfort" },
  { value: 0, label: "Balanced" },
  { value: 0.5, label: "Leaning performance" },
  { value: 1, label: "Max performance" },
];

const TOE_SHAPE_HINTS: Record<(typeof TOE_SHAPES)[number], string> = {
  egyptian: "big toe longest",
  greek: "second toe longest",
  roman: "first toes roughly even",
};

const INITIAL_FORM: SurveyFormState = {
  foot_width: "",
  instep: "",
  toe_shape: "",
  arch: "",
  heel_fit: "",
  street_size: "",
  discipline: "",
  terrain: "",
  level: "",
  goal: null,
  budget_cap_usd: "",
  goodAnchors: [],
  badAnchors: [],
};

const CONTROL_CLASS =
  "min-h-11 rounded-control border border-control-border bg-background px-3 text-foreground placeholder:text-muted";

type ShoesState = "loading" | "ready" | "failed";

export function SurveyForm() {
  const router = useRouter();
  const goalHintId = useId();
  const [form, setForm] = useState<SurveyFormState>(INITIAL_FORM);
  const [shoes, setShoes] = useState<Shoe[]>([]);
  const [shoesState, setShoesState] = useState<ShoesState>("loading");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const isInFlight = useRef(false);
  const errorBoxRef = useRef<HTMLElement>(null);
  const errorHeadingId = useId();

  useEffect(() => {
    if (errors.length > 0) errorBoxRef.current?.focus();
  }, [errors]);

  useEffect(() => {
    let isCurrent = true;
    getShoes().then(
      (loaded) => {
        if (!isCurrent) return;
        setShoes(loaded);
        setShoesState("ready");
      },
      () => {
        if (isCurrent) setShoesState("failed");
      },
    );
    return () => {
      isCurrent = false;
    };
  }, []);

  function setField(key: FieldKey, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function handleDisciplineChange(value: string) {
    setForm((prev) => ({
      ...prev,
      discipline: value as SurveyFormState["discipline"],
      // Goal is only meaningful per discipline, so clearing it drops the answer too.
      goal: value === "" ? null : prev.goal,
    }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // State updates are async, so a second submit before re-render would slip past isSubmitting.
    if (isInFlight.current) return;
    isInFlight.current = true;
    setIsSubmitting(true);
    setErrors([]);
    try {
      const result = await submitSurvey(toSurveyPayload(form));
      if (!result.ok) {
        setErrors(result.errors);
        isInFlight.current = false;
        setIsSubmitting(false);
        return;
      }
      try {
        sessionStorage.setItem(SURVEY_TOKEN_KEY, result.surveyToken);
      } catch {
        // Storage blocked: results will show the empty state, but the save succeeded.
      }
      router.push("/results");
    } catch (error) {
      setErrors([error instanceof ApiError ? error.message : "Something went wrong. Please try again."]);
      isInFlight.current = false;
      setIsSubmitting(false);
    }
  }

  const select = (key: FieldKey, label: string, options: Option[]) => (
    <Field label={label}>
      {(id) => (
        <select
          id={id}
          value={form[key]}
          onChange={(event) => setField(key, event.target.value)}
          className={CONTROL_CLASS}
        >
          <option value="">Prefer not to say</option>
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      )}
    </Field>
  );

  const hasDiscipline = form.discipline !== "";

  return (
    <form noValidate onSubmit={handleSubmit} className="mt-8 flex flex-col gap-8">
      <fieldset className="flex flex-col gap-4">
        <legend className="mb-2 text-xl font-semibold">Your foot</legend>
        {select("foot_width", "Foot width", toOptions(FOOT_WIDTHS))}
        {select("instep", "Instep", toOptions(INSTEPS))}
        {select(
          "toe_shape",
          "Toe shape",
          TOE_SHAPES.map((v) => ({ value: v, label: `${capitalize(v)} (${TOE_SHAPE_HINTS[v]})` })),
        )}
        {select("arch", "Arch", toOptions(ARCHES))}
        {select("heel_fit", "Heel fit", toOptions(HEEL_FITS))}
        <Field label="Street shoe size (US)">
          {(id) => (
            <input
              id={id}
              type="number"
              inputMode="decimal"
              step={0.5}
              min={0}
              max={20}
              value={form.street_size}
              onChange={(event) => setField("street_size", event.target.value)}
              className={CONTROL_CLASS}
            />
          )}
        </Field>
      </fieldset>

      <fieldset className="flex flex-col gap-4">
        <legend className="mb-2 text-xl font-semibold">How you climb</legend>
        <Field label="Discipline">
          {(id) => (
            <select
              id={id}
              value={form.discipline}
              onChange={(event) => handleDisciplineChange(event.target.value)}
              className={CONTROL_CLASS}
            >
              <option value="">Prefer not to say</option>
              {toOptions(DISCIPLINES).map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          )}
        </Field>
        {select("terrain", "Terrain", toOptions(TERRAINS))}
        {select("level", "Level", toOptions(LEVELS))}

        <fieldset aria-describedby={goalHintId} className="flex flex-col gap-2">
          <legend className="font-medium">Comfort or performance?</legend>
          <p id={goalHintId} className="text-sm text-muted">
            {hasDiscipline
              ? "Pick where you land between comfort and performance."
              : "Choose a discipline first to set this."}
          </p>
          {GOAL_OPTIONS.map((option) => (
            <label key={option.value} className="flex min-h-11 items-center gap-2">
              <input
                type="radio"
                name="goal"
                value={option.value}
                disabled={!hasDiscipline}
                checked={form.goal === option.value}
                onChange={() => setForm((prev) => ({ ...prev, goal: option.value }))}
              />
              {option.label}
            </label>
          ))}
        </fieldset>

        <Field label="Budget (USD)">
          {(id) => (
            <input
              id={id}
              type="number"
              inputMode="numeric"
              min={0}
              value={form.budget_cap_usd}
              onChange={(event) => setField("budget_cap_usd", event.target.value)}
              className={CONTROL_CLASS}
            />
          )}
        </Field>
      </fieldset>

      <fieldset className="flex flex-col gap-4">
        <legend className="mb-2 text-xl font-semibold">Shoes you know</legend>
        <p role="status" className="text-sm text-muted">
          {shoesState === "loading" && "Loading shoes…"}
          {shoesState === "failed" &&
            "Couldn't load the shoe list — you can still submit without anchors"}
        </p>
        <AnchorPicker
          label="Shoes that fit you well"
          shoes={shoes}
          value={form.goodAnchors}
          onChange={(next) => setForm((prev) => ({ ...prev, goodAnchors: next }))}
        />
        <AnchorPicker
          label="Shoes that fit you badly"
          shoes={shoes}
          value={form.badAnchors}
          onChange={(next) => setForm((prev) => ({ ...prev, badAnchors: next }))}
        />
      </fieldset>

      {errors.length > 0 && (
        <section
          ref={errorBoxRef}
          tabIndex={-1}
          aria-labelledby={errorHeadingId}
          className="rounded-control border border-danger p-3 text-danger"
        >
          <h2 id={errorHeadingId} className="font-semibold">
            We couldn&apos;t save your survey
          </h2>
          <ul className="list-inside list-disc">
            {errors.map((message, index) => (
              <li key={index}>{message}</li>
            ))}
          </ul>
        </section>
      )}

      <button
        type="submit"
        disabled={isSubmitting}
        aria-busy={isSubmitting}
        className="min-h-11 rounded-control bg-accent px-6 font-medium text-accent-foreground disabled:opacity-60"
      >
        Find my shoes
      </button>
    </form>
  );
}

function Field({ label, children }: { label: string; children: (id: string) => ReactNode }) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="font-medium">
        {label}
      </label>
      {children(id)}
    </div>
  );
}

function capitalize(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function toOptions(values: readonly string[]): Option[] {
  return values.map((value) => ({ value, label: capitalize(value) }));
}
