type Props = {
  options: number[];
  value: number;
  onChange: (value: number) => void;
};

export default function DurationToggle({ options, value, onChange }: Props) {
  return (
    <div className="duration-toggle" role="group" aria-label="Meeting duration">
      {options.map((option) => (
        <button
          key={option}
          aria-pressed={value === option}
          onClick={() => onChange(option)}
        >
          {option} min
        </button>
      ))}
    </div>
  );
}
