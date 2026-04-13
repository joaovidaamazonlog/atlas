/**
 * PartnerPopup.tsx
 * ================
 * Componente React que renderiza o popup de um parceiro.
 * Usa dangerouslySetInnerHTML com o HTML gerado por getPartnerPopupHtml.
 */

import { getPartnerPopupHtml } from '../../../lib/popupUtils';
import type { Partner } from '../../../store/types';

interface PartnerPopupProps {
  partner: Partner;
}

export default function PartnerPopup({ partner }: PartnerPopupProps) {
  return (
    <div dangerouslySetInnerHTML={{ __html: getPartnerPopupHtml(partner) }} />
  );
}
