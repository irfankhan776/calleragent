import { useQuery } from '@tanstack/react-query';
import api from '../api/client';

export function useStats() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['stats'],
    queryFn: () => api.getStats(),
    refetchInterval: 30000, // Poll stats every 30 seconds
  });

  const defaultStats = {
    total_calls: 0,
    today_calls: 0,
    outcomes: {
      Interested: 0,
      Callback: 0,
      Pitched: 0,
      "Not interested": 0
    },
    avg_duration_seconds: 0,
    recordings_saved: 0,
    sentiment_breakdown: {
      Positive: 0,
      Neutral: 0,
      Negative: 0
    },
    calls_by_hour: []
  };

  return {
    stats: data || defaultStats,
    isLoading,
    error,
    refetch
  };
}
