export default function OverlapSlider({
  value,
  onChange,
}: {
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="filter">
      <span>
        Minimum overlap <strong>{value} days</strong>
      </span>
      <input
        aria-label="Minimum construction overlap in days"
        type="range"
        min="1"
        max="180"
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
      <small>
        <span>1 day</span>
        <span>180 days</span>
      </small>
    </label>
  );
}
