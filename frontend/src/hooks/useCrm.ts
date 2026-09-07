import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createActivity,
  createSalesOpportunity,
  fetchCrmAnalytics,
  fetchFollowUps,
  fetchLeadActivities,
  fetchLeadTimeline,
  fetchNextBestAction,
  fetchPipelineBoard,
  fetchSalesOpportunities,
  fetchStatusHistory,
  promoteCandidate,
  setFollowUpStatus,
  setOpportunityStage,
  transitionLead,
} from '@/services/crm';
import { leadKeys } from '@/hooks/useLeads';
import { useToast } from '@/contexts/ToastContext';
import type { ApiErrorShape } from '@/services/api';
import type {
  CreateActivityBody,
  CreateSalesOpportunityBody,
  FollowUpParams,
  FollowUpStatus,
  SalesOpportunityParams,
  SetOpportunityStageBody,
  TransitionLeadBody,
} from '@/services/crm';

const errText = (e: unknown, fallback: string) =>
  (e as ApiErrorShape | undefined)?.message ?? fallback;

/** Centralized query keys for the CRM / sales-pipeline layer. */
export const crmKeys = {
  all: ['crm'] as const,
  analytics: ['crm', 'analytics'] as const,
  pipeline: ['crm', 'pipeline-board'] as const,
  opportunities: (params: SalesOpportunityParams) =>
    ['crm', 'opportunities', params] as const,
  followUps: (params: FollowUpParams) => ['crm', 'follow-ups', params] as const,
  timeline: (id: number) => ['crm', 'timeline', id] as const,
  statusHistory: (id: number) => ['crm', 'status-history', id] as const,
  nextBestAction: (id: number) => ['crm', 'next-best-action', id] as const,
  activities: (id: number) => ['crm', 'activities', id] as const,
};

// --- Queries ---------------------------------------------------------------

export function useCrmAnalytics() {
  return useQuery({
    queryKey: crmKeys.analytics,
    queryFn: ({ signal }) => fetchCrmAnalytics(signal),
  });
}

export function usePipelineBoard() {
  return useQuery({
    queryKey: crmKeys.pipeline,
    queryFn: ({ signal }) => fetchPipelineBoard(signal),
  });
}

export function useSalesOpportunities(params: SalesOpportunityParams = {}) {
  return useQuery({
    queryKey: crmKeys.opportunities(params),
    queryFn: ({ signal }) => fetchSalesOpportunities(params, signal),
  });
}

export function useFollowUps(params: FollowUpParams = {}) {
  return useQuery({
    queryKey: crmKeys.followUps(params),
    queryFn: ({ signal }) => fetchFollowUps(params, signal),
  });
}

export function useLeadTimeline(id: number) {
  return useQuery({
    queryKey: crmKeys.timeline(id),
    queryFn: ({ signal }) => fetchLeadTimeline(id, signal),
    enabled: Number.isFinite(id),
  });
}

export function useStatusHistory(id: number) {
  return useQuery({
    queryKey: crmKeys.statusHistory(id),
    queryFn: ({ signal }) => fetchStatusHistory(id, signal),
    enabled: Number.isFinite(id),
  });
}

export function useNextBestAction(id: number) {
  return useQuery({
    queryKey: crmKeys.nextBestAction(id),
    queryFn: ({ signal }) => fetchNextBestAction(id, signal),
    enabled: Number.isFinite(id),
  });
}

export function useLeadActivities(id: number) {
  return useQuery({
    queryKey: crmKeys.activities(id),
    queryFn: ({ signal }) => fetchLeadActivities(id, signal),
    enabled: Number.isFinite(id),
  });
}

// --- Mutations -------------------------------------------------------------

export function useTransitionLead(id: number) {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: (body: TransitionLeadBody) => transitionLead(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: crmKeys.all });
      qc.invalidateQueries({ queryKey: leadKeys.detail(id) });
      qc.invalidateQueries({ queryKey: leadKeys.all });
      toast.success('Lead status updated.');
    },
    onError: (e) => toast.error(errText(e, 'Unable to update the lead status.')),
  });
}

export function useCreateActivity() {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: (body: CreateActivityBody) => createActivity(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: crmKeys.all });
      toast.success('Activity logged.');
    },
    onError: (e) => toast.error(errText(e, 'Unable to log the activity.')),
  });
}

export function useCreateSalesOpportunity() {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: (body: CreateSalesOpportunityBody) => createSalesOpportunity(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: crmKeys.all });
      toast.success('Opportunity created.');
    },
    onError: (e) => toast.error(errText(e, 'Unable to create the opportunity.')),
  });
}

export function useSetOpportunityStage() {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: SetOpportunityStageBody }) =>
      setOpportunityStage(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: crmKeys.all });
      toast.success('Opportunity stage updated.');
    },
    onError: (e) => toast.error(errText(e, 'Unable to update the opportunity stage.')),
  });
}

export function usePromoteCandidate() {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: (id: number) => promoteCandidate(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: crmKeys.all });
      toast.success('Candidate promoted to an opportunity.');
    },
    onError: (e) => toast.error(errText(e, 'Unable to promote the candidate.')),
  });
}

export function useSetFollowUpStatus() {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: ({ id, status }: { id: number; status: FollowUpStatus }) =>
      setFollowUpStatus(id, status),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: crmKeys.all });
      toast.success('Follow-up updated.');
    },
    onError: (e) => toast.error(errText(e, 'Unable to update the follow-up.')),
  });
}
