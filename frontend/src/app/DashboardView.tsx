import { MetricTile } from "../components/MetricTile";
import { QueueList } from "../components/QueueList";
import {
  analystViews,
  evidenceBands,
  hypothesisQueues,
  metrics,
  researchQueues
} from "./dashboardData";

export function DashboardView() {
  return (
    <>
      <section className="metric-grid" aria-label="研究概览">
        {metrics.map((metric) => (
          <MetricTile key={metric.label} metric={metric} />
        ))}
      </section>

      <section className="primary-layout">
        <div className="main-column">
          <section className="research-board" aria-labelledby="research-board-heading">
            <div className="panel-heading">
              <h2 id="research-board-heading">研究闭环</h2>
            </div>
            <div className="evidence-grid">
              {evidenceBands.map((band) => {
                const Icon = band.icon;

                return (
                  <div className="evidence-band" key={band.label}>
                    <Icon aria-hidden="true" size={20} />
                    <strong>{band.label}</strong>
                  </div>
                );
              })}
            </div>
            <div className="analyst-strip" aria-label="MVP 分析视角">
              {analystViews.map((view) => (
                <span key={view}>{view}</span>
              ))}
            </div>
          </section>

          <QueueList title="开发队列" items={researchQueues} />
        </div>

        <aside className="side-column" aria-label="假设与风险">
          <QueueList title="假设追踪" items={hypothesisQueues} />
          <section className="work-panel valuation-panel" aria-labelledby="valuation-heading">
            <div className="panel-heading">
              <h2 id="valuation-heading">估值实验室</h2>
            </div>
            <div className="valuation-scale" aria-label="估值区间">
              <span className="scale-segment scale-segment--buy">买入区</span>
              <span className="scale-segment scale-segment--watch">观察区</span>
              <span className="scale-segment scale-segment--avoid">回避区</span>
            </div>
          </section>
        </aside>
      </section>
    </>
  );
}
