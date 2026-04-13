/**
 * ComparisonPopup.tsx
 * ===================
 * Componente React que renderiza o popup de comparação entre dois parceiros.
 * Usa dangerouslySetInnerHTML com o HTML gerado por getComparisonPopupHtml.
 */

import { getComparisonPopupHtml } from '../../../lib/popupUtils';
import type { Partner } from '../../../store/types';

interface ComparisonPopupProps {
  partner1: Partner;
  partner2: Partner;
}

export default function ComparisonPopup({ partner1, partner2 }: ComparisonPopupProps) {
  return (
    <div
      dangerouslySetInnerHTML={{ __html: getComparisonPopupHtml(partner1, partner2) }}
    />
  );
}
