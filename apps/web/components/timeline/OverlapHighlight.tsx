export default function OverlapHighlight({
  left,
  width,
}: {
  left: number;
  width: number;
}) {
  return (
    <div
      className="overlap-highlight"
      style={{ left: `${left}%`, width: `${width}%` }}
      aria-label="Shared construction interval"
    />
  );
}
