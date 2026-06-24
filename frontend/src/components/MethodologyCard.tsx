interface MethodologyCardProps {
  index: string;
  title: string;
  children: React.ReactNode;
}

export default function MethodologyCard({ index, title, children }: MethodologyCardProps) {
  return (
    <article className="method-card">
      <div className="method-index">{index}</div>
      <div>
        <h3>{title}</h3>
        <div className="method-copy">{children}</div>
      </div>
    </article>
  );
}
