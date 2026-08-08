type StatusPillProps = {
  status: "online" | "offline" | "checking";
  label: string;
};

export function StatusPill({ status, label }: StatusPillProps) {
  return <span className={`status-pill status-pill--${status}`}>{label}</span>;
}

