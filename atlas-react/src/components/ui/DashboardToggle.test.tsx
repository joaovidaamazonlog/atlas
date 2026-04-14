/**
 * DashboardToggle.test.tsx
 * ========================
 * Testes unitários para o componente DashboardToggle.
 *
 * **Validates: Requirements 3.4, 3.5, 3.8**
 */

import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { DashboardToggle } from './DashboardToggle';

describe('DashboardToggle', () => {
  it('renderiza com aria-label "Abrir dashboard" quando fechado', () => {
    const { getByRole } = render(<DashboardToggle isOpen={false} onClick={() => {}} />);
    const btn = getByRole('button', { name: 'Abrir dashboard' });
    expect(btn).toBeTruthy();
  });

  it('renderiza com aria-label "Fechar dashboard" quando aberto', () => {
    const { getByRole } = render(<DashboardToggle isOpen={true} onClick={() => {}} />);
    const btn = getByRole('button', { name: 'Fechar dashboard' });
    expect(btn).toBeTruthy();
  });

  it('chama onClick ao clicar no botão', () => {
    const handleClick = vi.fn();
    const { getByRole } = render(<DashboardToggle isOpen={false} onClick={handleClick} />);
    fireEvent.click(getByRole('button'));
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it('aria-expanded é false quando isOpen=false', () => {
    const { getByRole } = render(<DashboardToggle isOpen={false} onClick={() => {}} />);
    const btn = getByRole('button');
    expect(btn.getAttribute('aria-expanded')).toBe('false');
  });

  it('aria-expanded é true quando isOpen=true', () => {
    const { getByRole } = render(<DashboardToggle isOpen={true} onClick={() => {}} />);
    const btn = getByRole('button');
    expect(btn.getAttribute('aria-expanded')).toBe('true');
  });

  it('backgroundColor é var(--color-navy) quando isOpen=false', () => {
    const { getByRole } = render(<DashboardToggle isOpen={false} onClick={() => {}} />);
    const btn = getByRole('button') as HTMLButtonElement;
    expect(btn.style.backgroundColor).toBe('var(--color-navy)');
  });

  it('backgroundColor é var(--color-accent) quando isOpen=true', () => {
    const { getByRole } = render(<DashboardToggle isOpen={true} onClick={() => {}} />);
    const btn = getByRole('button') as HTMLButtonElement;
    expect(btn.style.backgroundColor).toBe('var(--color-accent)');
  });

  it('tem borderRadius "40px 0 0 40px" (semi-círculo esquerdo)', () => {
    const { getByRole } = render(<DashboardToggle isOpen={false} onClick={() => {}} />);
    const btn = getByRole('button') as HTMLButtonElement;
    expect(btn.style.borderRadius).toBe('40px 0 0 40px');
  });
});
