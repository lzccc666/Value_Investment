import type { Metric } from "../app/dashboardData";

type MetricTileProps = {
  metric: Metric;
};

export function MetricTile({ metric }: MetricTileProps) {
  return (
    <section className={`metric-tile metric-tile--${metric.tone}`} aria-label={metric.label}>
      <span>{metric.label}</span>
      <strong className={metric.valueStyle === "compact" ? "metric-tile__value--compact" : undefined}>
        {metric.value}
      </strong>
      <small>{metric.trend}</small>
    </section>
  );
}
