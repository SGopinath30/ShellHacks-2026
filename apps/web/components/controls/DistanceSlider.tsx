export default function DistanceSlider({
  value,
  onChange,
  max = 25,
}: {
  value: number;
  onChange: (value: number) => void;
  max?: number;
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
        max={max}
        step="0.1"
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
      <small>
        <span>0.1 mi</span>
        <span>{max} mi</span>
      </small>
    </label>
  );
}
