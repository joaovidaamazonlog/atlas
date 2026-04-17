/**
 * StyleTab.tsx
 * ============
 * Aba de estilização do mapa.
 * Selects "Estilizar por" e "Detalhar por" + checkboxes de camadas.
 */

import { useStore } from '../../store';

const STYLE_FIELD_OPTIONS = [
  { value: 'delivery_station', label: 'Delivery Station' },
  { value: 'status', label: 'Status' },
  { value: 'hub_delivey_initiatives', label: 'Hub Delivery Initiatives' },
  { value: 'supply_run', label: 'Supply Run' },
  { value: 'bucket_ade', label: 'Carteira' },
];

interface CheckboxRowProps {
  id: string;
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}

function CheckboxRow({ id, label, checked, onChange }: CheckboxRowProps) {
  return (
    <label
      htmlFor={id}
      className={[
        'flex items-center gap-3 px-3 py-3 rounded cursor-pointer',
        'transition-colors duration-150 hover:bg-white/5',
        'min-h-[44px]',
      ].join(' ')}
    >
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="w-4 h-4 accent-atlas-accent cursor-pointer"
      />
      <span className="text-sm text-atlas-light">{label}</span>
    </label>
  );
}

export default function StyleTab() {
  const styleConfig = useStore((s) => s.styleConfig);
  const setStyleConfig = useStore((s) => s.setStyleConfig);

  return (
    <div className="p-3">
      {/* Estilizar por */}
      <div className="mb-3">
        <label
          htmlFor="style-primary"
          className="block text-xs font-medium text-atlas-muted mb-1"
        >
          Estilizar por
        </label>
        <select
          id="style-primary"
          value={styleConfig.primaryField}
          onChange={(e) => setStyleConfig({ primaryField: e.target.value })}
          className={[
            'w-full px-3 py-2 rounded bg-atlas-darker border border-white/10',
            'text-sm text-atlas-light',
            'focus:outline-none focus:border-atlas-accent transition-colors duration-150',
            'min-h-[44px]',
          ].join(' ')}
        >
          {STYLE_FIELD_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* Detalhar por */}
      <div className="mb-4">
        <label
          htmlFor="style-secondary"
          className="block text-xs font-medium text-atlas-muted mb-1"
        >
          Detalhar por
        </label>
        <select
          id="style-secondary"
          value={styleConfig.secondaryField}
          onChange={(e) => setStyleConfig({ secondaryField: e.target.value })}
          className={[
            'w-full px-3 py-2 rounded bg-atlas-darker border border-white/10',
            'text-sm text-atlas-light',
            'focus:outline-none focus:border-atlas-accent transition-colors duration-150',
            'min-h-[44px]',
          ].join(' ')}
        >
          {STYLE_FIELD_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* Camadas */}
      <div className="border-t border-white/10 pt-2">
        <p className="text-xs font-medium text-atlas-muted px-3 py-2">Camadas</p>
        <CheckboxRow
          id="layer-radii"
          label="Exibir Raios"
          checked={styleConfig.showRadii}
          onChange={(v) => setStyleConfig({ showRadii: v })}
        />
        <CheckboxRow
          id="layer-polygons"
          label="Exibir Áreas de Prospecção"
          checked={styleConfig.showPolygons}
          onChange={(v) => setStyleConfig({ showPolygons: v })}
        />
        <CheckboxRow
          id="layer-jurisdictions"
          label="Exibir Jurisdições"
          checked={styleConfig.showJurisdictions}
          onChange={(v) => setStyleConfig({ showJurisdictions: v })}
        />
        <CheckboxRow
          id="layer-optimization"
          label="Exibir Camada de Otimização"
          checked={styleConfig.showOptimizationLayer}
          onChange={(v) => setStyleConfig({ showOptimizationLayer: v })}
        />
        <CheckboxRow
          id="layer-geo-intelligence"
          label="Exibir Geointeligência"
          checked={styleConfig.showGeoIntelligence}
          onChange={(v) => setStyleConfig({ showGeoIntelligence: v })}
        />
        <CheckboxRow
          id="layer-geo-intelligence"
          label="Exibir Geointeligência"
          checked={styleConfig.showGeoIntelligence}
          onChange={(v) => setStyleConfig({ showGeoIntelligence: v })}
        />
      </div>
    </div>
  );
}
