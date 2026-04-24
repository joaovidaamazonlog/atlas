/**
 * StyleTab.tsx
 * ============
 * Aba de estilização do mapa.
 * Selects "Estilizar por" e "Detalhar por" + checkboxes de camadas.
 */

import { useTranslation } from 'react-i18next';
import { useStore } from '../../store';

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
        'transition-colors duration-150 hover:bg-atlas-dark',
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
  const { t } = useTranslation();
  const styleConfig = useStore((s) => s.styleConfig);
  const setStyleConfig = useStore((s) => s.setStyleConfig);

  const STYLE_FIELD_OPTIONS = [
    { value: 'delivery_station', label: t('style.field_delivery_station') },
    { value: 'status', label: t('style.field_status') },
    { value: 'hub_delivey_initiatives', label: t('style.field_initiatives') },
    { value: 'supply_run', label: t('style.field_supply_run') },
    { value: 'bucket_ade', label: t('style.field_bucket') },
  ];

  return (
    <div className="p-3">
      {/* Estilizar por */}
      <div className="mb-3">
        <label
          htmlFor="style-primary"
          className="block text-xs font-medium text-atlas-muted mb-1"
        >
          {t('style.primary_label')}
        </label>
        <select
          id="style-primary"
          value={styleConfig.primaryField}
          onChange={(e) => setStyleConfig({ primaryField: e.target.value })}
          className={[
            'w-full px-3 py-2 rounded bg-atlas-darker border border-[var(--border-color)]',
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
          {t('style.secondary_label')}
        </label>
        <select
          id="style-secondary"
          value={styleConfig.secondaryField}
          onChange={(e) => setStyleConfig({ secondaryField: e.target.value })}
          className={[
            'w-full px-3 py-2 rounded bg-atlas-darker border border-[var(--border-color)]',
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
      <div className="border-t border-[var(--border-color)] pt-2">
        <p className="text-xs font-medium text-atlas-muted px-3 py-2">{t('style.layers_title')}</p>
        <CheckboxRow
          id="layer-radii"
          label={t('style.layer_radii')}
          checked={styleConfig.showRadii}
          onChange={(v) => setStyleConfig({ showRadii: v })}
        />
        <CheckboxRow
          id="layer-polygons"
          label={t('style.layer_polygons')}
          checked={styleConfig.showPolygons}
          onChange={(v) => setStyleConfig({ showPolygons: v })}
        />
        {styleConfig.showPolygons && (
          <div className="px-3 pb-2">
            <label className="block text-xs font-medium text-atlas-muted mb-1">
              {t('style.polygon_color_label')}
            </label>
            <select
              value={styleConfig.polygonColorField}
              onChange={(e) => setStyleConfig({ polygonColorField: e.target.value })}
              className="w-full px-3 py-2 rounded bg-atlas-darker border border-[var(--border-color)] text-sm text-atlas-light focus:outline-none focus:border-atlas-accent transition-colors min-h-[44px]"
            >
              <option value="attainment">{t('style.polygon_color_attainment')}</option>
              <option value="territory">{t('style.polygon_color_territory')}</option>
              <option value="ds">{t('style.polygon_color_ds')}</option>
              <option value="ctl">{t('style.polygon_color_ctl')}</option>
              <option value="bdm">{t('style.polygon_color_bdm')}</option>
            </select>
          </div>
        )}
        <CheckboxRow
          id="layer-jurisdictions"
          label={t('style.layer_jurisdictions')}
          checked={styleConfig.showJurisdictions}
          onChange={(v) => setStyleConfig({ showJurisdictions: v })}
        />

        <CheckboxRow
          id="layer-geo-intelligence"
          label={t('style.layer_geo_intelligence')}
          checked={styleConfig.showGeoIntelligence}
          onChange={(v) => setStyleConfig({ showGeoIntelligence: v })}
        />
      </div>
    </div>
  );
}
