import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  approveDraft,
  cancelDraft,
  editDraft,
  fetchDraft,
  fetchDrafts,
  fetchProviderStatus,
  generateDraft,
  sendDraft,
} from '@/services/outreachApi';
import { useToast } from '@/contexts/ToastContext';
import type { ApiErrorShape } from '@/services/api';
import type { DraftListParams, EditDraftBody, GenerateDraftBody } from '@/services/outreachApi';

const errText = (e: unknown, fallback: string) =>
  (e as ApiErrorShape | undefined)?.message ?? fallback;

/** Centralized query keys for the real outreach-draft layer. */
export const outreachApiKeys = {
  all: ['outreach-api'] as const,
  drafts: (params: DraftListParams) => ['outreach-api', 'drafts', params] as const,
  draft: (id: number) => ['outreach-api', 'draft', id] as const,
  providers: ['outreach-api', 'providers'] as const,
};

// --- Queries ---------------------------------------------------------------

export function useDrafts(params: DraftListParams = {}) {
  return useQuery({
    queryKey: outreachApiKeys.drafts(params),
    queryFn: ({ signal }) => fetchDrafts(params, signal),
  });
}

export function useDraft(id: number) {
  return useQuery({
    queryKey: outreachApiKeys.draft(id),
    queryFn: ({ signal }) => fetchDraft(id, signal),
    enabled: Number.isFinite(id),
  });
}

export function useProviderStatus() {
  return useQuery({
    queryKey: outreachApiKeys.providers,
    queryFn: ({ signal }) => fetchProviderStatus(signal),
  });
}

// --- Mutations -------------------------------------------------------------

export function useGenerateDraft() {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: (body: GenerateDraftBody) => generateDraft(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: outreachApiKeys.all });
      toast.success('Outreach draft generated.');
    },
    onError: (e) => toast.error(errText(e, 'Unable to generate the outreach draft.')),
  });
}

export function useEditDraft() {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: EditDraftBody }) => editDraft(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: outreachApiKeys.all });
      toast.success('Draft updated.');
    },
    onError: (e) => toast.error(errText(e, 'Unable to update the draft.')),
  });
}

export function useApproveDraft() {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: (id: number) => approveDraft(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: outreachApiKeys.all });
      toast.success('Draft approved.');
    },
    onError: (e) => toast.error(errText(e, 'Unable to approve the draft.')),
  });
}

export function useCancelDraft() {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: (id: number) => cancelDraft(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: outreachApiKeys.all });
      toast.success('Draft cancelled.');
    },
    onError: (e) => toast.error(errText(e, 'Unable to cancel the draft.')),
  });
}

export function useSendDraft() {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: (id: number) => sendDraft(id),
    // Never imply a send succeeded unless the backend returns status === "SENT".
    onSuccess: (draft) => {
      qc.invalidateQueries({ queryKey: outreachApiKeys.all });
      if (draft.status === 'SENT') {
        toast.success('Message sent.');
      } else if (draft.status === 'FAILED') {
        toast.error(draft.error ?? 'Send failed.');
      } else {
        toast.error('The message was not sent.');
      }
    },
    onError: (e) => toast.error(errText(e, 'Unable to send the message.')),
  });
}
