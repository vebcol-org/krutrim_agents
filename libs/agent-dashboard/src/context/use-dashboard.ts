import { useContext } from 'react';
import { DashboardContext, type DashboardContextValue } from './dashboard-context';

export function useDashboard(): DashboardContextValue {
  const ctx = useContext(DashboardContext);
  if (!ctx) {
    throw new Error('useDashboard() must be called within an <AgentDashboard> (DashboardProvider not found in the tree).');
  }
  return ctx;
}
