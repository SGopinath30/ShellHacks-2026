export default function DistanceSlider({
  value,
  onChange,
}: {
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="filter">
      <span>
        Maximum distance <strong>{value.toFixed(1)} mi</strong>
      </span>
      <input
        aria-label="Maximum distance in miles"
        type="range"
        min="0.1"
        max="12"
        step="0.1"
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
      <small>
        <span>0.1 mi</span>
        <span>12 mi</span>
      </small>
    </label>
  );
}
