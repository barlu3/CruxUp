"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";

import { PLOT_PADDING, VIEW_SIZE, toChartPoint } from "../lib/quadrant-scale";
import { formatAxisValue } from "../lib/format-axis-value";
import { QUADRANT_LABEL } from "../lib/quadrant-labels";
import { toShoeLabel } from "../lib/shoe-label";
import type { PriorSource, QuadrantShoe } from "../lib/types";

interface QuadrantChartProps {
  shoes: QuadrantShoe[];
  target?: { x: number; y: number };
  highlightIds?: readonly string[];
}

type PointState = "default" | "highlighted" | "dimmed";

const PROVENANCE_LABEL: Record<PriorSource, string> = {
  hand: "Hand-placed",
  spec: "Spec-derived",
  corpus: "Corpus-derived",
};
const ANCHOR_LABEL = "Section 3 reference shoe";
const MARK_RADIUS = 5;
const ANCHOR_RADIUS = 7;
// Transparent target so a point is easy to hit without enlarging the mark. The svg is fluid, so
// size it for the narrowest case: 328px phone content width (360 - 2x16 gutters) gives
// 40 * 328 / 480 = ~27px >= 24px. Overlap in dense clusters is fine; keyboard reaches every shoe.
const HIT_RADIUS = 20;
const NEUTRAL_THRESHOLD = 0.05;
const FOCUS_RING_RADIUS = 11;
const TARGET_ARM = 10;
const PLOT_END = VIEW_SIZE - PLOT_PADDING;
const CENTER = VIEW_SIZE / 2;

export function QuadrantChart({ shoes, target, highlightIds }: QuadrantChartProps) {
  const baseId = useId();
  const titleId = `${baseId}-title`;
  const instructionsId = `${baseId}-instructions`;
  const wrapperRef = useRef<HTMLDivElement>(null);
  const pointRefs = useRef(new Map<string, SVGGElement>());
  const [tabStopId, setTabStopId] = useState<string | null>(null);
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [isTooltipDismissed, setIsTooltipDismissed] = useState(false);

  const ordered = useMemo(() => sortShoes(shoes), [shoes]);
  const highlightSet = useMemo(() => new Set(highlightIds), [highlightIds]);
  const isHighlightActive = highlightSet.size > 0;
  const activeId = hoveredId ?? focusedId;
  const tooltipShoe = isTooltipDismissed ? undefined : ordered.find((shoe) => shoe.id === activeId);

  // Document-level so Escape also dismisses a tooltip opened by hover alone (WCAG 1.4.13).
  const isTooltipShown = tooltipShoe !== undefined;
  useEffect(() => {
    if (!isTooltipShown) return;
    function handleDocumentKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape") setIsTooltipDismissed(true);
    }
    // Touch has no mouseleave, so a tap elsewhere is the only way to clear a hover tooltip.
    function handleDocumentPointerDown(event: PointerEvent) {
      if (!wrapperRef.current?.contains(event.target as Node)) setHoveredId(null);
    }
    document.addEventListener("keydown", handleDocumentKeyDown);
    document.addEventListener("pointerdown", handleDocumentPointerDown);
    return () => {
      document.removeEventListener("keydown", handleDocumentKeyDown);
      document.removeEventListener("pointerdown", handleDocumentPointerDown);
    };
  }, [isTooltipShown]);

  if (shoes.length === 0) {
    return <p className="text-muted">No shoes to show</p>;
  }

  const effectiveTabStopId = ordered.some((s) => s.id === tabStopId) ? tabStopId : ordered[0].id;
  const hasCorpus = shoes.some((s) => s.prior_source === "corpus");
  const hasHand = shoes.some((s) => s.prior_source === "hand");
  const hasSpec = shoes.some((s) => s.prior_source === "spec");
  const hasAnchor = shoes.some((s) => s.is_anchor);
  const hasHighlighted = isHighlightActive && shoes.some((s) => highlightSet.has(s.id));

  function handleKeyDown(event: KeyboardEvent<SVGGElement>, index: number) {
    const lastIndex = ordered.length - 1;
    let next: number;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") next = Math.min(index + 1, lastIndex);
    else if (event.key === "ArrowLeft" || event.key === "ArrowUp") next = Math.max(index - 1, 0);
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = lastIndex;
    else return;
    event.preventDefault();
    pointRefs.current.get(ordered[next].id)?.focus();
  }

  function toState(shoe: QuadrantShoe): PointState {
    if (!isHighlightActive) return "default";
    return highlightSet.has(shoe.id) ? "highlighted" : "dimmed";
  }

  return (
    <figure className="flex flex-col gap-3">
      <div ref={wrapperRef} className="relative">
        <svg
          viewBox={`0 0 ${VIEW_SIZE} ${VIEW_SIZE}`}
          role="group"
          aria-labelledby={titleId}
          aria-describedby={instructionsId}
          className="block h-auto w-full"
        >
          <title id={titleId}>Shoe quadrant chart: comfort to performance, stiff to soft</title>
          <Frame />
          <g className="fill-muted text-xs" aria-hidden="true">
            <text x={PLOT_PADDING - 8} y={CENTER} textAnchor="end" dominantBaseline="middle">Comfort</text>
            <text x={PLOT_END + 8} y={CENTER} textAnchor="start" dominantBaseline="middle">Performance</text>
            <text x={CENTER} y={PLOT_PADDING - 32} textAnchor="middle">Soft</text>
            <text x={CENTER} y={PLOT_END + 36} textAnchor="middle">Stiff</text>
            {/* Outside the frame so no dot or anchor label can sit on a quadrant label. */}
            <text x={PLOT_END} y={PLOT_END + 16} textAnchor="end">{QUADRANT_LABEL.Q1}</text>
            <text x={PLOT_PADDING} y={PLOT_END + 16} textAnchor="start">{QUADRANT_LABEL.Q2}</text>
            <text x={PLOT_PADDING} y={PLOT_PADDING - 12} textAnchor="start">{QUADRANT_LABEL.Q3}</text>
            <text x={PLOT_END} y={PLOT_PADDING - 12} textAnchor="end">{QUADRANT_LABEL.Q4}</text>
          </g>
          {ordered.map((shoe, index) => {
            const { cx, cy } = toChartPoint(shoe.x, shoe.y);
            const state = toState(shoe);
            const isFocused = focusedId === shoe.id;
            const radius = shoe.is_anchor ? ANCHOR_RADIUS : MARK_RADIUS;
            const isLabelLeft = shoe.x > 0.6;
            return (
              <g
                key={shoe.id}
                ref={(node) => {
                  if (node) pointRefs.current.set(shoe.id, node);
                  else pointRefs.current.delete(shoe.id);
                }}
                role="img"
                aria-roledescription="shoe"
                aria-label={toPointName(shoe, state === "highlighted")}
                tabIndex={shoe.id === effectiveTabStopId ? 0 : -1}
                data-state={state === "default" ? undefined : state}
                className={`outline-none ${toFillClass(shoe, state)}`}
                onKeyDown={(event) => handleKeyDown(event, index)}
                onFocus={() => {
                  setTabStopId(shoe.id);
                  setFocusedId(shoe.id);
                  setIsTooltipDismissed(false);
                }}
                onBlur={() => setFocusedId(null)}
                onMouseEnter={() => {
                  setHoveredId(shoe.id);
                  setIsTooltipDismissed(false);
                }}
                onMouseLeave={() => setHoveredId(null)}
                onPointerLeave={() => setHoveredId(null)}
              >
                <circle cx={cx} cy={cy} r={HIT_RADIUS} className="fill-transparent stroke-none" />
                {isFocused && (
                  <circle cx={cx} cy={cy} r={FOCUS_RING_RADIUS} strokeWidth={2} className="fill-none stroke-focus-ring" />
                )}
                <Mark shoe={shoe} state={state} cx={cx} cy={cy} r={radius} />
                {shoe.is_anchor && (
                  <text
                    x={isLabelLeft ? cx - radius - 6 : cx + radius + 6}
                    y={cy}
                    textAnchor={isLabelLeft ? "end" : "start"}
                    dominantBaseline="middle"
                    className="fill-foreground text-xs"
                  >
                    {toShortName(shoe)}
                  </text>
                )}
              </g>
            );
          })}
          {target && <Target x={target.x} y={target.y} />}
        </svg>
        <p id={instructionsId} className="sr-only">
          Use the arrow keys to move between shoes from most comfort-focused to most
          performance-focused; Home and End jump to the ends; Escape hides the details.
        </p>
        {tooltipShoe && <Tooltip shoe={tooltipShoe} isHighlighted={toState(tooltipShoe) === "highlighted"} />}
      </div>
      <ul aria-label="Legend" className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-foreground">
        {hasHand && <LegendItem label={PROVENANCE_LABEL.hand} swatch={<Swatch kind="hand" />} />}
        {hasSpec && <LegendItem label={PROVENANCE_LABEL.spec} swatch={<Swatch kind="spec" />} />}
        {hasCorpus && <LegendItem label={PROVENANCE_LABEL.corpus} swatch={<Swatch kind="corpus" />} />}
        {hasAnchor && <LegendItem label={ANCHOR_LABEL} swatch={<Swatch kind="anchor" />} />}
        {target && <LegendItem label="Your target" swatch={<Swatch kind="target" />} />}
        {hasHighlighted && <LegendItem label="Highlighted" swatch={<Swatch kind="highlighted" />} />}
      </ul>
    </figure>
  );
}

function Frame() {
  const quarter = (PLOT_END - PLOT_PADDING) / 4;
  const line = (key: string, x1: number, y1: number, x2: number, y2: number, className = "stroke-border") => (
    <line key={key} x1={x1} y1={y1} x2={x2} y2={y2} strokeWidth={1} vectorEffect="non-scaling-stroke" className={className} />
  );
  return (
    <g aria-hidden="true">
      <rect
        x={PLOT_PADDING}
        y={PLOT_PADDING}
        width={PLOT_END - PLOT_PADDING}
        height={PLOT_END - PLOT_PADDING}
        strokeWidth={1}
        vectorEffect="non-scaling-stroke"
        className="fill-none stroke-border"
      />
      {line("grid-v1", PLOT_PADDING + quarter, PLOT_PADDING, PLOT_PADDING + quarter, PLOT_END)}
      {line("grid-v3", PLOT_PADDING + 3 * quarter, PLOT_PADDING, PLOT_PADDING + 3 * quarter, PLOT_END)}
      {line("grid-h1", PLOT_PADDING, PLOT_PADDING + quarter, PLOT_END, PLOT_PADDING + quarter)}
      {line("grid-h3", PLOT_PADDING, PLOT_PADDING + 3 * quarter, PLOT_END, PLOT_PADDING + 3 * quarter)}
      {line("axis-x", PLOT_PADDING, CENTER, PLOT_END, CENTER, "stroke-muted")}
      {line("axis-y", CENTER, PLOT_PADDING, CENTER, PLOT_END, "stroke-muted")}
    </g>
  );
}

function Mark({ shoe, state, cx, cy, r }: { shoe: QuadrantShoe; state: PointState; cx: number; cy: number; r: number }) {
  const strokeClass = toStrokeClass(shoe, state);
  const strokeWidth = shoe.is_anchor || (state === "highlighted" && shoe.prior_source === "spec") ? 3 : 2;
  if (shoe.prior_source === "corpus") {
    return <rect x={cx - r} y={cy - r} width={2 * r} height={2 * r} strokeWidth={strokeWidth} className={strokeClass} />;
  }
  return <circle cx={cx} cy={cy} r={r} strokeWidth={strokeWidth} className={strokeClass} />;
}

function Target({ x, y }: { x: number; y: number }) {
  const { cx, cy } = toChartPoint(x, y);
  return (
    <g role="img" aria-label="Your target" className="stroke-accent" strokeWidth={2}>
      <circle cx={cx} cy={cy} r={TARGET_ARM - 3} className="fill-none" />
      <line x1={cx - TARGET_ARM - 4} y1={cy} x2={cx + TARGET_ARM + 4} y2={cy} />
      <line x1={cx} y1={cy - TARGET_ARM - 4} x2={cx} y2={cy + TARGET_ARM + 4} />
    </g>
  );
}

// aria-hidden and a duplicate of the point's accessible name, so pointer-events-none is
// acceptable under WCAG 1.4.13: nothing here needs to be hoverable or reachable.
function Tooltip({ shoe, isHighlighted }: { shoe: QuadrantShoe; isHighlighted: boolean }) {
  const { cx, cy } = toChartPoint(shoe.x, shoe.y);
  const horizontal = shoe.x > 0.5 ? "-translate-x-[calc(100%+0.75rem)]" : "translate-x-3";
  const vertical = shoe.y > 0.7 ? "translate-y-3" : "-translate-y-[calc(100%+0.75rem)]";
  return (
    <div
      role="tooltip"
      aria-hidden="true"
      style={{ left: `${(cx / VIEW_SIZE) * 100}%`, top: `${(cy / VIEW_SIZE) * 100}%` }}
      className={`pointer-events-none absolute z-10 w-max max-w-64 rounded-control border border-control-border bg-surface px-3 py-2 text-sm text-foreground ${horizontal} ${vertical}`}
    >
      <strong className="block">{toShoeLabel(shoe)}</strong>
      {toDetailSentences(shoe, isHighlighted).map((sentence) => (
        <span key={sentence} className="block">
          {sentence}
        </span>
      ))}
    </div>
  );
}

function LegendItem({ label, swatch }: { label: string; swatch: React.ReactNode }) {
  return (
    <li className="flex items-center gap-2">
      {swatch}
      <span>{label}</span>
    </li>
  );
}

type SwatchKind = "hand" | "spec" | "corpus" | "anchor" | "target" | "highlighted";

function Swatch({ kind }: { kind: SwatchKind }) {
  return (
    <svg viewBox="0 0 20 20" width={20} height={20} aria-hidden="true" className="shrink-0">
      {kind === "hand" && <circle cx={10} cy={10} r={5} strokeWidth={2} className="fill-foreground stroke-background" />}
      {kind === "spec" && <circle cx={10} cy={10} r={5} strokeWidth={2} className="fill-background stroke-foreground" />}
      {kind === "corpus" && <rect x={5} y={5} width={10} height={10} strokeWidth={2} className="fill-foreground stroke-background" />}
      {kind === "anchor" && <circle cx={10} cy={10} r={7} strokeWidth={3} className="fill-foreground stroke-foreground" />}
      {kind === "highlighted" && <circle cx={10} cy={10} r={5} strokeWidth={2} className="fill-accent stroke-background" />}
      {kind === "target" && (
        <g className="stroke-accent" strokeWidth={2}>
          <circle cx={10} cy={10} r={4} className="fill-none" />
          <line x1={1} y1={10} x2={19} y2={10} />
          <line x1={10} y1={1} x2={10} y2={19} />
        </g>
      )}
    </svg>
  );
}

function sortShoes(shoes: QuadrantShoe[]): QuadrantShoe[] {
  return [...shoes].sort(
    (a, b) => a.x - b.x || b.y - a.y || toShoeLabel(a).localeCompare(toShoeLabel(b)),
  );
}

// Fill is set on the group so the mark inherits it; the hit area and focus ring override it.
function toFillClass(shoe: QuadrantShoe, state: PointState): string {
  // Provenance survives a highlight: spec points stay hollow.
  if (shoe.prior_source === "spec") return "fill-background";
  if (state === "highlighted") return "fill-accent";
  // With a highlight active every point is accent or muted, so muted is only ever compared
  // against accent, never against the default foreground.
  return state === "dimmed" ? "fill-muted" : "fill-foreground";
}

function toStrokeClass(shoe: QuadrantShoe, state: PointState): string {
  if (shoe.prior_source === "spec" && state === "highlighted") return "stroke-accent";
  if (shoe.is_anchor) return "stroke-foreground";
  if (shoe.prior_source === "spec") return state === "dimmed" ? "stroke-muted" : "stroke-foreground";
  return "stroke-background";
}

function toPointName(shoe: QuadrantShoe, isHighlighted: boolean): string {
  return [`${toShoeLabel(shoe)}.`, ...toDetailSentences(shoe, isHighlighted)].join(" ");
}

// Shared by the accessible name and the tooltip so both say the same thing.
function toDetailSentences(shoe: QuadrantShoe, isHighlighted: boolean): string[] {
  return [
    `Comfort–performance ${formatAxisValue(shoe.x)}, ${toSide(shoe.x, "comfort", "performance")}.`,
    `Stiff–soft ${formatAxisValue(shoe.y)}, ${toSide(shoe.y, "stiff", "soft")}.`,
    `${PROVENANCE_LABEL[shoe.prior_source]}.`,
    ...(shoe.is_anchor ? [`${ANCHOR_LABEL}.`] : []),
    ...(isHighlighted ? ["Highlighted."] : []),
  ];
}

function toSide(value: number, negative: string, positive: string): string {
  if (Math.abs(value) < NEUTRAL_THRESHOLD) return "neutral";
  return `leaning ${value < 0 ? negative : positive}`;
}

function toShortName(shoe: QuadrantShoe): string {
  return [shoe.model, shoe.version].filter((part) => part !== "").join(" ");
}
