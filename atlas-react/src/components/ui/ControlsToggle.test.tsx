/**
 * ControlsToggle.test.tsx
 * =======================
 * Testes unitários para o componente ControlsToggle.
 *
 * **Validates: Requirements 4.4, 4.6, 4.8, 4.9**
 */

import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { ControlsToggle } from './ControlsToggle';

describe('ControlsToggle', () => {
  it('renderiza com aria-label "Abrir controles" quando fechado', () => {
    const { getByRole } = render(<ControlsToggle isOpen={false} onClick={() => {}} />);
    const btn = getByRole('button', { name: 'Abrir controles' });
    expect(btn).toBeTruthy();
  });

  it('renderiza com aria-label "Fechar controles" quando aberto', () => {
    const { getByRole } = render(<ControlsToggle isOpen={true} onClick={() => {}} />);
    const btn = getByRole('button', { name: 'Fechar controles' });
    expect(btn).toBeTruthy();
  });

  it('chama onClick ao clicar no botão', () => {
    const handleClick = vi.fn();
    const { getByRole } = render(<ControlsToggle isOpen={false} onClick={handleClick} />);
    fireEvent.click(getByRole('button'));
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it('aria-expanded é false quando isOpen=false', () => {
    const { getByRole } = render(<ControlsToggle isOpen={false} onClick={() => {}} />);
    const btn = getByRole('button');
    expect(btn.getAttribute('aria-expanded')).toBe('false');
  });

  it('aria-expanded é true quando isOpen=true', () => {
    const { getByRole } = render(<ControlsToggle isOpen={true} onClick={() => {}} />);
    const btn = getByRole('button');
    expect(btn.getAttribute('aria-expanded')).toBe('true');
  });

  it('backgroundColor é var(--color-navy) quando isOpen=false', () => {
    const { getByRole } = render(<ControlsToggle isOpen={false} onClick={() => {}} />);
    const btn = getByRole('button') as HTMLButtonElement;
    expect(btn.style.backgroundColor).toBe('var(--color-navy)');
  });

  it('backgroundColor é var(--color-accent) quando isOpen=true', () => {
    const { getByRole } = render(<ControlsToggle isOpen={true} onClick={() => {}} />);
    const btn = getByRole('button') as HTMLButtonElement;
    expect(btn.style.backgroundColor).toBe('var(--color-accent)');
  });

  it('exibe ícone hamburger (rects) quando fechado', () => {
    const { getByRole } = render(<ControlsToggle isOpen={false} onClick={() => {}} />);
    const btn = getByRole('button');
    // Hamburger uses <rect> elements, X icon uses <line> elements
    const rects = btn.querySelectorAll('rect');
    const lines = btn.querySelectorAll('line');
    expect(rects.length).toBeGreaterThan(0);
    expect(lines.length).toBe(0);
  });

  it('exibe ícone X (lines) quando aberto', () => {
    const { getByRole } = render(<ControlsToggle isOpen={true} onClick={() => {}} />);
    const btn = getByRole('button');
    // X icon uses <line> elements, hamburger uses <rect> elements
    const lines = btn.querySelectorAll('line');
    const rects = btn.querySelectorAll('rect');
    expect(lines.length).toBeGreaterThan(0);
    expect(rects.length).toBe(0);
  });

  it('tem borderRadius "0 40px 40px 0" (semi-círculo direito)', () => {
    const { getByRole } = render(<ControlsToggle isOpen={false} onClick={() => {}} />);
    const btn = getByRole('button') as HTMLButtonElement;
    expect(btn.style.borderRadius).toBe('0 40px 40px 0');
  });
});
