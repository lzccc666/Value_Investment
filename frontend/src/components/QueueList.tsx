import type { QueueItem } from "../app/dashboardData";

type QueueListProps = {
  title: string;
  items: QueueItem[];
};

export function QueueList({ title, items }: QueueListProps) {
  return (
    <section className="work-panel" aria-labelledby={`${title}-heading`}>
      <div className="panel-heading">
        <h2 id={`${title}-heading`}>{title}</h2>
      </div>
      <ul className="queue-list">
        {items.map((item) => (
          <li key={item.title} className="queue-row">
            <div>
              <strong>{item.title}</strong>
              <span>{item.meta}</span>
            </div>
            <span className={`priority priority--${item.priority}`}>{item.priority}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

