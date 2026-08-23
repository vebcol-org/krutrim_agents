import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { CategoricalFilter } from '../../src/filters/categorical-filter';
import { RangeFilter } from '../../src/filters/range-filter';
import { DateRangeFilter } from '../../src/filters/date-range-filter';
import { BooleanFilter } from '../../src/filters/boolean-filter';
import { SearchFilter } from '../../src/filters/search-filter';
import type { Filter } from '../../src/types';

afterEach(cleanup);

const baseFilter: Filter = { id: 'f1', field: 'region', dataSourceId: 'ds', type: 'categorical', appliesTo: ['*'] };

describe('CategoricalFilter', () => {
  it('reports the selected options on change', () => {
    const onChange = vi.fn();
    render(<CategoricalFilter filter={baseFilter} value={[]} options={['us', 'eu']} onChange={onChange} />);
    const select = screen.getByRole('listbox') as HTMLSelectElement;
    const usOption = screen.getByRole('option', { name: 'us' }) as HTMLOptionElement;
    usOption.selected = true;
    fireEvent.change(select);
    expect(onChange).toHaveBeenCalledWith(['us']);
  });
});

describe('RangeFilter', () => {
  it('reports [min, max] as numbers when either input changes', () => {
    const onChange = vi.fn();
    render(<RangeFilter filter={{ ...baseFilter, type: 'range' }} value={[0, 100]} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText(/minimum/i), { target: { value: '10' } });
    expect(onChange).toHaveBeenCalledWith([10, 100]);
  });
});

describe('DateRangeFilter', () => {
  it('reports [start, end] ISO strings', () => {
    const onChange = vi.fn();
    render(<DateRangeFilter filter={{ ...baseFilter, type: 'dateRange' }} value={['2026-01-01', '2026-01-31']} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText(/start/i), { target: { value: '2026-02-01' } });
    expect(onChange).toHaveBeenCalledWith(['2026-02-01', '2026-01-31']);
  });
});

describe('BooleanFilter', () => {
  it('reports the checked state', () => {
    const onChange = vi.fn();
    render(<BooleanFilter filter={{ ...baseFilter, type: 'boolean' }} value={false} onChange={onChange} />);
    fireEvent.click(screen.getByRole('checkbox'));
    expect(onChange).toHaveBeenCalledWith(true);
  });
});

describe('SearchFilter', () => {
  it('reports the query string as it is typed', () => {
    const onChange = vi.fn();
    render(<SearchFilter filter={{ ...baseFilter, type: 'search' }} value="" onChange={onChange} />);
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'acme' } });
    expect(onChange).toHaveBeenCalledWith('acme');
  });
});
