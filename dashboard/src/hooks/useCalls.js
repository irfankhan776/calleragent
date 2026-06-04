import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import api from '../api/client';

export function useCalls() {
  const [search, setSearch] = useState('');
  const [outcome, setOutcome] = useState('');
  const [date, setDate] = useState('');
  const [page, setPage] = useState(0); // 0-indexed page
  const limit = 20;

  // Reset page when filters change
  useEffect(() => {
    setPage(0);
  }, [search, outcome, date]);

  const offset = page * limit;

  const queryKey = ['calls', { search, outcome, date, limit, offset }];

  const { data, isLoading, error, refetch } = useQuery({
    queryKey,
    queryFn: () => api.getCalls({
      search: search || undefined,
      outcome: outcome || undefined,
      date: date || undefined,
      limit,
      offset,
      sort: 'called_at',
      order: 'desc'
    }),
    refetchInterval: 15000, // Auto-refresh every 15s
    placeholderData: (previousData) => previousData, // Smooth pagination transition
  });

  const calls = data?.calls || [];
  const total = data?.total || 0;

  const setFilter = (type, value) => {
    if (type === 'search') setSearch(value);
    if (type === 'outcome') setOutcome(value);
    if (type === 'date') setDate(value);
  };

  return {
    calls,
    total,
    isLoading,
    error,
    filters: { search, outcome, date },
    setFilter,
    page,
    limit,
    setPage,
    refetch
  };
}
