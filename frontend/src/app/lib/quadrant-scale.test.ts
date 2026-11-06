import { describe, expect, it } from "vitest";

import { PLOT_PADDING, VIEW_SIZE, toChartPoint } from "./quadrant-scale";

describe("toChartPoint", () => {
  it("maps (1, 1) to the top-right plot corner", () => {
    expect(toChartPoint(1, 1)).toEqual({ cx: VIEW_SIZE - PLOT_PADDING, cy: PLOT_PADDING });
  });

  it("maps (-1, -1) to the bottom-left plot corner", () => {
    expect(toChartPoint(-1, -1)).toEqual({ cx: PLOT_PADDING, cy: VIEW_SIZE - PLOT_PADDING });
  });

  it("maps (0, 0) to the centre", () => {
    expect(toChartPoint(0, 0)).toEqual({ cx: VIEW_SIZE / 2, cy: VIEW_SIZE / 2 });
  });

  it("puts a softer shoe higher up the chart", () => {
    expect(toChartPoint(0, 0.5).cy).toBeLessThan(toChartPoint(0, -0.5).cy);
  });
});
