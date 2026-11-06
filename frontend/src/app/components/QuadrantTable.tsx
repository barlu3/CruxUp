import { formatAxisValue } from "../lib/format-axis-value";
import { QUADRANT_LABEL } from "../lib/quadrant-labels";
import { shoeName } from "../lib/shoe";
import type { PriorSource, Quadrant, QuadrantShoe } from "../lib/types";

const PLACEMENT_LABEL: Record<PriorSource, string> = {
  hand: "Hand-placed",
  spec: "Spec-derived",
  corpus: "From reviews",
};
const QUADRANTS: readonly Quadrant[] = ["Q1", "Q2", "Q3", "Q4"];
const COLUMN_COUNT = 5;
const CELL_CLASS = "border border-border px-3 py-2 text-left";

export function QuadrantTable({ shoes }: { shoes: QuadrantShoe[] }) {
  return (
    <div
      role="region"
      aria-label="All shoes by quadrant, scrollable"
      tabIndex={0}
      className="overflow-x-auto"
    >
    <table className="w-full border-collapse text-sm text-foreground">
      <caption className="sr-only">All shoes by quadrant</caption>
      <thead>
        <tr>
          <th scope="col" className={CELL_CLASS}>Shoe</th>
          <th scope="col" className={CELL_CLASS}>Comfort–performance</th>
          <th scope="col" className={CELL_CLASS}>Stiff–soft</th>
          <th scope="col" className={CELL_CLASS}>Placement</th>
          <th scope="col" className={CELL_CLASS}>Section 3 reference</th>
        </tr>
      </thead>
      {QUADRANTS.map((quadrant) => {
        const group = shoes.filter((shoe) => shoe.quadrant === quadrant);
        return (
          <tbody key={quadrant}>
            <tr>
              <th scope="rowgroup" colSpan={COLUMN_COUNT} className={`${CELL_CLASS} bg-surface`}>
                {QUADRANT_LABEL[quadrant]}
              </th>
            </tr>
            {group.length === 0 ? (
              <tr>
                <td colSpan={COLUMN_COUNT} className={`${CELL_CLASS} text-muted`}>No shoes</td>
              </tr>
            ) : (
              group.map((shoe) => (
                <tr key={shoe.id}>
                  <td className={CELL_CLASS}>
                    {shoeName(shoe)}
                    <span className="sr-only"> ({QUADRANT_LABEL[quadrant]})</span>
                  </td>
                  <td className={CELL_CLASS}>{formatAxisValue(shoe.x)}</td>
                  <td className={CELL_CLASS}>{formatAxisValue(shoe.y)}</td>
                  <td className={CELL_CLASS}>{PLACEMENT_LABEL[shoe.prior_source]}</td>
                  <td className={CELL_CLASS}>{shoe.is_anchor ? "Yes" : ""}</td>
                </tr>
              ))
            )}
          </tbody>
        );
      })}
    </table>
    </div>
  );
}
