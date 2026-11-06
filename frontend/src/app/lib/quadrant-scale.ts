export const VIEW_SIZE = 480;
// Room outside the plot frame for the axis end labels.
export const PLOT_PADDING = 84;

const PLOT_SIZE = VIEW_SIZE - 2 * PLOT_PADDING;

export function toChartPoint(x: number, y: number): { cx: number; cy: number } {
  return {
    cx: PLOT_PADDING + ((x + 1) / 2) * PLOT_SIZE,
    // SVG y grows downward; soft (+1) belongs at the top.
    cy: PLOT_PADDING + ((1 - y) / 2) * PLOT_SIZE,
  };
}
