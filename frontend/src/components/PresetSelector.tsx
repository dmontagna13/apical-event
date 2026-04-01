import type { Preset } from "../types/api";

interface PresetSelectorProps {
  presets: Preset[];
  onLoad: (preset: Preset) => void;
  onSave: (name: string) => void;
}

export function PresetSelector({ presets, onLoad, onSave }: PresetSelectorProps): JSX.Element {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <label className="text-xs uppercase tracking-[0.2em] text-slate-400">
        Load preset
        <select
          className="mt-2 w-full min-w-[220px] rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm text-slate-700"
          defaultValue=""
          onChange={(event: { target: { value: string } }) => {
            const preset = presets.find((item) => item.name === event.target.value);
            if (preset) {
              onLoad(preset);
            }
          }}
        >
          <option value="">Select preset</option>
          {presets.map((preset) => (
            <option key={preset.name} value={preset.name}>
              {preset.name}
            </option>
          ))}
        </select>
      </label>
      <button
        type="button"
        onClick={() => {
          const name = window.prompt("Preset name");
          if (name) {
            onSave(name);
          }
        }}
        className="rounded-full border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-600"
      >
        Save as Preset
      </button>
    </div>
  );
}
