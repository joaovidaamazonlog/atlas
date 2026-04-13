/**
 * SlotPopup.tsx
 * =============
 * Componente React que renderiza o popup de um slot ideal.
 * Usa dangerouslySetInnerHTML com o HTML gerado por getSlotPopupHtml.
 */

import { getSlotPopupHtml } from '../../../lib/popupUtils';
import type { Partner } from '../../../store/types';

interface SlotPopupProps {
  partner: Partner;
}

export default function SlotPopup({ partner }: SlotPopupProps) {
  return (
    <div dangerouslySetInnerHTML={{ __html: getSlotPopupHtml(partner) }} />
  );
}
