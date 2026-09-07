// Types aligned with the FastAPI schemas (Prompt 10). Field names match the
// backend JSON exactly so responses can be consumed without remapping.

export type LeadPriority = 'HOT' | 'WARM' | 'NURTURE' | 'LOW';

export type LeadStatus =
  | 'NEW'
  | 'RESEARCHED'
  | 'CONTACTED'
  | 'REPLIED'
  | 'MEETING'
  | 'QUALIFIED'
  | 'PROPOSAL'
  | 'WON'
  | 'LOST'
  | 'NURTURE';

export type SignalType =
  | 'HIRING'
  | 'PROJECT_AWARD'
  | 'PROJECT_EXECUTION'
  | 'EXPANSION'
  | 'DIGITAL_TRANSFORMATION'
  | 'TECHNOLOGY_INITIATIVE'
  | 'VENDOR_REQUIREMENT'
  | 'CONTRACT'
  | 'OTHER';

export type DataProvenance = 'REAL' | 'SYNTHETIC';

export type VerificationStatus =
  | 'VERIFIED'
  | 'PARTIALLY_VERIFIED'
  | 'UNVERIFIED'
  | 'CONTRADICTED'
  | 'STALE';

export type LeadReadiness = 'READY' | 'REVIEW_REQUIRED' | 'HOLD' | 'DISCARD';

export type SourceTier = 'TIER_1' | 'TIER_2' | 'TIER_3' | 'TIER_4';

/** One evidence record supporting a lead. */
export interface EvidenceRecord {
  id: number;
  evidence_type: string;
  source_name: string | null;
  source_url: string | null;
  source_domain: string | null;
  source_tier: SourceTier;
  evidence_title: string | null;
  published_at: string | null;
  observed_at: string | null;
  source_reliability_score: number;
  freshness_score: number;
  evidence_confidence: number;
  independence_group_id: string | null;
  verification_status: VerificationStatus;
  data_provenance: DataProvenance;
}

export interface ConflictRecord {
  id: number;
  conflict_type: string;
  severity: string;
  description: string | null;
  resolution_status: string;
}

/** GET /leads/{id}/verification — the four distinct scores. */
export interface LeadVerification {
  lead_id: number;
  company_name: string;
  lead_score: number;
  lead_priority: LeadPriority;
  source_reliability: number;
  evidence_confidence: number;
  signal_confidence: number | null;
  freshness_score: number;
  verification_status: VerificationStatus;
  lead_readiness: LeadReadiness;
  independent_support_count: number;
  source_count: number;
  verification_reason: string | null;
  verified_at: string | null;
  supporting_sources: EvidenceRecord[];
  conflicts: ConflictRecord[];
  data_provenance: DataProvenance;
}

export type HiringIntensity = 'LOW' | 'MEDIUM' | 'HIGH' | 'VERY_HIGH';

export type CompanyType =
  | 'IT_SERVICES'
  | 'SOFTWARE_PRODUCT'
  | 'SAAS'
  | 'CLOUD'
  | 'AI_ML'
  | 'CYBERSECURITY'
  | 'FINTECH_TECH'
  | 'HEALTHTECH'
  | 'ECOMMERCE_TECH'
  | 'ENTERPRISE_SOFTWARE'
  | 'IT_CONSULTING'
  | 'DIGITAL_TRANSFORMATION'
  | 'OTHER_TECHNOLOGY';

/** One job posting supporting a company opportunity (evidence trail). */
export interface LeadEvidence {
  source?: string | null;
  source_id?: string | null;
  source_url?: string | null;
  job_title?: string | null;
  published_at?: string | null;
  external_id?: string | null;
  duplicate_of_prior_source?: boolean;
}

/** A stored lead (GET /leads/{id}, list items, POST /leads). */
export interface Lead {
  id: number;
  company_name: string;
  normalized_company_name: string | null;
  company_domain: string | null;
  company_type: CompanyType | null;
  industry: string | null;
  location: string | null;
  company_size: string | null;
  company_website: string | null;
  // Company-level hiring aggregation (one lead == one company opportunity).
  it_job_count: number;
  recent_job_count: number;
  hiring_intensity: HiringIntensity | null;
  primary_target_role: string | null;
  company_signals: string[];
  signal_type: SignalType | null;
  signal_title: string | null;
  signal_description: string | null;
  signal_date: string | null;
  source_name: string | null;
  source_url: string | null;
  technologies: string[];
  project_name: string | null;
  project_value: number | null;
  estimated_hiring: number | null;
  hiring_roles: string[];
  poc_name: string | null;
  poc_title: string | null;
  poc_linkedin_url: string | null;
  public_contact: string | null;
  signal_confidence: number | null;
  lead_score: number;
  lead_priority: LeadPriority;
  opportunity_summary: string | null;
  recommended_action: string | null;
  recommended_pitch: string | null;
  // Evidence / provenance.
  data_provenance: DataProvenance;
  source_count: number;
  evidence: LeadEvidence[];
  last_signal_date: string | null;
  // Verification intelligence — separate from lead_score (optional on the type so
  // older mocks stay valid; the API always populates them).
  source_reliability?: number;
  evidence_confidence?: number;
  freshness_score?: number;
  independent_support_count?: number;
  verification_status?: VerificationStatus;
  lead_readiness?: LeadReadiness;
  verification_reason?: string | null;
  verified_at?: string | null;
  status: LeadStatus;
  created_at: string | null;
  updated_at: string | null;
  last_verified_at: string | null;
}

/** GET /leads/technology-demand item. */
export interface TechnologyDemandItem {
  technology: string;
  openings: number;
  companies: number;
}

export interface TechnologyDemandResponse {
  provenance: DataProvenance | null;
  items: TechnologyDemandItem[];
}

/** Payload for POST /leads (direct create). Calculated fields are not allowed. */
export interface LeadCreate {
  company_name: string;
  industry?: string | null;
  location?: string | null;
  company_size?: string | null;
  company_website?: string | null;
  signal_type?: SignalType | null;
  signal_title?: string | null;
  signal_description?: string | null;
  signal_date?: string | null;
  source_name?: string | null;
  source_url?: string | null;
  technologies?: string[];
  project_name?: string | null;
  project_value?: number | null;
  estimated_hiring?: number | null;
  hiring_roles?: string[];
  poc_name?: string | null;
  poc_title?: string | null;
  poc_linkedin_url?: string | null;
  public_contact?: string | null;
  signal_confidence?: number | null;
  status?: LeadStatus;
}

/** Payload for PUT /leads/{id} (partial). Calculated fields are rejected by the API. */
export type LeadUpdate = Partial<LeadCreate>;

/** Request body for POST /leads/analyze. */
export type LeadAnalyzeRequest = Omit<LeadCreate, 'signal_type' | 'status'>;

// --- Analysis engine outputs (subset used by the UI) ----------------------

export interface DetectedSignalDetail {
  signal_type: SignalType;
  detected_keywords: string[];
  reason: string;
}

export interface SignalAnalysis {
  signal_types: SignalType[];
  signals: DetectedSignalDetail[];
  signal_strength: number;
  signal_strength_label: string;
  detected_keywords: string[];
  detected_technologies: string[];
  estimated_hiring: number | null;
  detected_roles: string[];
  reasons?: string[];
}

export type StaffingNeed = 'HIGH' | 'MEDIUM' | 'LOW' | 'UNKNOWN';
export type Urgency = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'UNKNOWN';

export interface OpportunityAnalysis {
  opportunity_type: string;
  secondary_opportunity_types: string[];
  potential_staffing_need: StaffingNeed;
  likely_roles: string[];
  likely_technologies: string[];
  estimated_team_size_min: number | null;
  estimated_team_size_max: number | null;
  urgency: Urgency;
  business_reason: string;
  recommended_next_step: string;
  opportunity_confidence: number;
  opportunity_confidence_label: string;
}

export interface RoleRecommendation {
  role: string;
  role_category: string;
  decision_maker_type: string;
  relevance_score: number;
  reason: string;
}

export interface POCRecommendation {
  primary_role: RoleRecommendation | null;
  secondary_roles: RoleRecommendation[];
  recommendation_confidence: number;
  recommendation_confidence_label: string;
  reason: string;
}

export interface ScoreBreakdown {
  large_technology_hiring: number;
  new_project_or_contract: number;
  enterprise_project: number;
  multiple_openings: number;
  expansion_or_transformation: number;
  technology_match: number;
  decision_maker: number;
  recency: number;
}

export interface LeadScoreResult {
  score: number;
  priority: LeadPriority;
  score_breakdown: ScoreBreakdown;
  positive_signals: string[];
  negative_signals: string[];
  explanation: string;
  scoring_confidence: number;
  scoring_confidence_label: string;
}

export interface PitchResult {
  email_subject: string;
  opening_message: string;
  value_proposition: string;
  recommended_pitch: string;
  call_to_action: string;
  linkedin_message: string;
  call_talking_points: string[];
  target_role: string | null;
  message_strategy: string;
  confidence: number;
  confidence_label: string;
}

/** Response of POST /leads/analyze (LeadAnalysisResult). */
export interface LeadAnalysis {
  lead_id: number | null;
  company_name: string;
  signal_analysis: SignalAnalysis;
  opportunity_analysis: OpportunityAnalysis;
  scoring_result: LeadScoreResult;
  poc_recommendation: POCRecommendation;
  pitch_result: PitchResult;
  final_score: number;
  priority: LeadPriority;
  recommended_action: string | null;
  status: string;
  already_existed: boolean;
}

/** Paginated list response (GET /leads). */
export interface LeadListResponse {
  items: Lead[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface LeadListParams {
  page?: number;
  page_size?: number;
  search?: string;
  industry?: string;
  location?: string;
  signal_type?: SignalType;
  lead_priority?: LeadPriority;
  status?: LeadStatus;
  min_score?: number;
  max_score?: number;
  technology?: string;
  provenance?: 'real' | 'synthetic' | 'all';
  sort_by?: 'lead_score' | 'created_at' | 'updated_at' | 'signal_date' | 'company_name';
  sort_order?: 'asc' | 'desc';
}
