import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ClipboardCopy,
  Database,
  Download,
  FileText,
  RefreshCw,
  ShieldCheck,
  Upload,
  Wrench,
} from "lucide-react";
import {
  type ChangeEvent,
  type KeyboardEvent,
  type ReactNode,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { ApiProblemError, DataForgeClient } from "./api";
import { getRuntimeConfig } from "./config";
import {
  DEFAULT_MAX_UPLOAD_BYTES,
  buildEvidenceExport,
  formatRows,
  groupIssues,
  parseCsvPreview,
  problemToMessage,
  validateCsvFile,
} from "./csv";
import type {
  AnalyzeResponse,
  BackendCapability,
  ConstraintCandidate,
  CsvPreview,
  DatasetInput,
  IssueGroup,
  ProblemDetail,
  RepairFailure,
  RepairReadiness,
  RiskLevel,
  Severity,
  VerifiedFix,
} from "./types";

const SAMPLE_OPTIONS = [
  { value: "hospital_10rows", label: "Hospital", detail: "Healthcare data" },
  { value: "flights_10rows", label: "Flights", detail: "Aviation data" },
  { value: "beers_10rows", label: "Beers", detail: "Consumer data" },
];

const TABS = [
  { id: "risk", label: "Risk" },
  { id: "repairs", label: "Repairs" },
  { id: "receipt", label: "Receipt" },
] as const;

type TabId = (typeof TABS)[number]["id"];
type WorkState = "idle" | "loading" | "ready" | "error";
type SortKey = "severity" | "count" | "column";

function App() {
  const runtimeConfig = useMemo(() => getRuntimeConfig(), []);
  const client = useMemo(
    () => new DataForgeClient(runtimeConfig.BACKEND_URL),
    [runtimeConfig.BACKEND_URL],
  );
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [capability, setCapability] = useState<BackendCapability | null>(null);
  const [backendState, setBackendState] = useState<WorkState>("loading");
  const [datasetState, setDatasetState] = useState<WorkState>("idle");
  const [dataset, setDataset] = useState<DatasetInput | null>(null);
  const [advanced, setAdvanced] = useState(false);
  const [activeTab, setActiveTab] = useState<TabId>("risk");
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null);
  const [analysisState, setAnalysisState] = useState<WorkState>("idle");
  const [acceptedConstraintIds, setAcceptedConstraintIds] = useState<string[]>([]);
  const [problem, setProblem] = useState<ProblemDetail | null>(null);
  const [filter, setFilter] = useState("");
  const [severityFilter, setSeverityFilter] = useState<Severity | "all">("all");
  const [sortKey, setSortKey] = useState<SortKey>("severity");
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");

  const maxUploadBytes = capability?.max_upload_bytes ?? DEFAULT_MAX_UPLOAD_BYTES;
  const busy = datasetState === "loading" || analysisState === "loading";
  const canRun = backendState === "ready" && dataset !== null && !busy;
  const evidenceText = useMemo(
    () => (analysis && dataset ? buildEvidenceExport(dataset.file.name, analysis) : ""),
    [analysis, dataset],
  );
  const groupedIssues = useMemo(() => groupIssues(analysis?.issues ?? []), [analysis]);
  const visibleIssues = useMemo(
    () => filterAndSortIssues(groupedIssues, filter, severityFilter, sortKey),
    [filter, groupedIssues, severityFilter, sortKey],
  );

  useEffect(() => {
    let cancelled = false;

    async function warmBackend() {
      setBackendState("loading");
      for (let attempt = 0; attempt < 6; attempt += 1) {
        try {
          const health = await client.health();
          if (!cancelled) {
            setCapability(health);
            setAdvanced((current) => current && health.advanced_available);
            setBackendState("ready");
          }
          return;
        } catch {
          await sleep(Math.min(750 * 2 ** attempt, 6_000));
        }
      }
      if (!cancelled) {
        setBackendState("error");
        setCapability(null);
      }
    }

    void warmBackend();
    return () => {
      cancelled = true;
    };
  }, [client]);

  async function adoptFile(file: File, source: DatasetInput["source"], sampleName?: string) {
    setDatasetState("loading");
    setProblem(null);

    const validation = validateCsvFile(file, maxUploadBytes);
    if (!validation.ok) {
      setDatasetState("error");
      setProblem(localProblem(validation.message ?? "The CSV file could not be accepted."));
      return;
    }

    try {
      const preview = parseCsvPreview(await file.text());
      setDataset({ file, source, sampleName, preview });
      setDatasetState("ready");
      setAnalysis(null);
      setAcceptedConstraintIds([]);
      setCopyState("idle");
      setAnalysisState("idle");
      setActiveTab("risk");
    } catch (error) {
      setDatasetState("error");
      setProblem(localProblem(error instanceof Error ? error.message : "The CSV preview failed."));
    }
  }

  async function chooseSample(sampleName: string) {
    if (!sampleName || busy) {
      return;
    }
    try {
      const file = await client.sample(sampleName);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      await adoptFile(file, "sample", sampleName);
    } catch (error) {
      setDatasetState("error");
      setProblem(problemFromUnknown(error));
    }
  }

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const [file] = event.target.files ?? [];
    if (file) {
      await adoptFile(file, "upload");
    }
  }

  async function runAnalyze(ids: string[]) {
    if (!dataset || !canRun) {
      return;
    }
    setAnalysisState("loading");
    setProblem(null);
    setCopyState("idle");
    setActiveTab("risk");
    try {
      const nextAnalysis = await client.analyze(dataset.file, advanced, ids);
      setAnalysis(nextAnalysis);
      setAcceptedConstraintIds(
        nextAnalysis.schema_inference.candidates
          .filter((candidate) => candidate.decision === "accepted")
          .map((candidate) => candidate.candidate_id),
      );
      setAnalysisState("ready");
    } catch (error) {
      const nextProblem = problemFromUnknown(error);
      setAnalysisState("error");
      setProblem(nextProblem);
      if (nextProblem.error === "advanced_mode_unavailable") {
        setAdvanced(false);
        setCapability((current) =>
          current ? { ...current, advanced_available: false } : current,
        );
      }
    }
  }

  function toggleConstraint(candidateId: string, checked: boolean) {
    setAcceptedConstraintIds((current) => {
      if (checked) {
        return current.includes(candidateId) ? current : [...current, candidateId];
      }
      return current.filter((id) => id !== candidateId);
    });
  }

  async function copyEvidence() {
    if (!evidenceText) {
      return;
    }
    try {
      await navigator.clipboard.writeText(evidenceText);
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }
  }

  function exportEvidence() {
    if (!evidenceText || !dataset) {
      return;
    }
    const url = URL.createObjectURL(new Blob([evidenceText], { type: "application/json" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${dataset.file.name.replace(/\.csv$/i, "")}-dataforge-dry-run.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  function handleTabKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    const index = TABS.findIndex((tab) => tab.id === activeTab);
    if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      event.preventDefault();
      const direction = event.key === "ArrowRight" ? 1 : -1;
      setActiveTab(TABS[(index + direction + TABS.length) % TABS.length].id);
    }
    if (event.key === "Home") {
      event.preventDefault();
      setActiveTab(TABS[0].id);
    }
    if (event.key === "End") {
      event.preventDefault();
      setActiveTab(TABS[TABS.length - 1].id);
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar" aria-label="DataForge command bar">
        <div className="brand-lockup">
          <span className="product-mark" aria-hidden="true">DF</span>
          <div>
            <p className="eyebrow">DataForge Playground</p>
            <h1>Verified CSV repair workbench</h1>
          </div>
        </div>
        <div className="command-meta" aria-label="Playground operating constraints">
          <span>Stateless dry run</span>
          <span>{Math.floor(maxUploadBytes / 1024)} KiB CSV cap</span>
          <BackendStatus state={backendState} capability={capability} onRetry={() => window.location.reload()} />
        </div>
      </header>

      <main className="workspace" aria-busy={busy}>
        <section className="panel intake-panel" aria-labelledby="intake-title">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Input</p>
              <h2 id="intake-title">Dataset intake</h2>
            </div>
            <span className="limit-pill">{Math.floor(maxUploadBytes / 1024)} KiB limit</span>
          </div>

          <label className="file-drop" htmlFor="csv-upload">
            <Upload aria-hidden="true" />
            <span>
              <strong>Upload CSV</strong>
              <small>{dataset?.source === "upload" ? dataset.file.name : "No file selected"}</small>
            </span>
            <input
              id="csv-upload"
              ref={fileInputRef}
              type="file"
              accept=".csv,text/csv"
              disabled={busy}
              onChange={handleFileChange}
            />
          </label>

          <div className="sample-grid" aria-label="Sample datasets">
            {SAMPLE_OPTIONS.map((sample) => (
              <button
                className="sample-button"
                type="button"
                key={sample.value}
                disabled={busy}
                onClick={() => void chooseSample(sample.value)}
              >
                <Database aria-hidden="true" />
                <span>
                  <strong>{sample.label}</strong>
                  <small>{sample.detail}</small>
                </span>
              </button>
            ))}
          </div>

          <label className="switch-row" htmlFor="advanced-mode">
            <span>
              <strong>Advanced mode</strong>
              <small>
                {capability?.advanced_available
                  ? "Backend provider available"
                  : "Backend provider unavailable"}
              </small>
            </span>
            <input
              id="advanced-mode"
              type="checkbox"
              role="switch"
              checked={advanced}
              disabled={busy || !capability?.advanced_available}
              onChange={(event) => setAdvanced(event.target.checked)}
            />
          </label>

          <div className="action-row">
            <button className="primary-action" type="button" disabled={!canRun} onClick={() => void runAnalyze([])}>
              <Activity aria-hidden="true" />
              Analyze
            </button>
            <button
              className="secondary-action"
              type="button"
              disabled={!canRun || acceptedConstraintIds.length === 0}
              onClick={() => void runAnalyze(acceptedConstraintIds)}
            >
              <RefreshCw aria-hidden="true" />
              Rerun with accepted constraints
            </button>
          </div>
        </section>

        <section className="panel preview-panel" aria-labelledby="preview-title">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Preview</p>
              <h2 id="preview-title">Current CSV</h2>
            </div>
            <DatasetBadge dataset={dataset} />
          </div>
          {dataset ? (
            <CsvPreviewTable preview={dataset.preview} />
          ) : (
            <EmptyState
              icon={<FileText aria-hidden="true" />}
              title="No dataset loaded"
              body="Choose a sample or upload a CSV to inspect the first rows before backend analysis."
            />
          )}
        </section>

        <section className="panel results-panel" aria-labelledby="results-title">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Evidence</p>
              <h2 id="results-title">Proof loop</h2>
            </div>
            {analysis ? (
              <div className="evidence-actions">
                <button type="button" className="icon-button" onClick={() => void copyEvidence()}>
                  <ClipboardCopy aria-hidden="true" />
                  {copyState === "copied" ? "Copied" : copyState === "failed" ? "Copy failed" : "Copy"}
                </button>
                <button type="button" className="icon-button" onClick={exportEvidence}>
                  <Download aria-hidden="true" />
                  Export
                </button>
              </div>
            ) : null}
          </div>

          {problem ? <ProblemBanner problem={problem} /> : null}
          {copyState === "failed" && evidenceText ? (
            <CopyFallback evidenceText={evidenceText} />
          ) : null}

          <div className="tabs" role="tablist" aria-label="Result views">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                id={`tab-${tab.id}`}
                role="tab"
                type="button"
                aria-selected={activeTab === tab.id}
                aria-controls={`panel-${tab.id}`}
                tabIndex={activeTab === tab.id ? 0 : -1}
                onClick={() => setActiveTab(tab.id)}
                onKeyDown={handleTabKeyDown}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <ResultPanel id="risk" activeTab={activeTab}>
            <RiskView
              state={analysisState}
              analysis={analysis}
              issues={visibleIssues}
              filter={filter}
              severityFilter={severityFilter}
              sortKey={sortKey}
              selectedConstraintIds={acceptedConstraintIds}
              onFilterChange={setFilter}
              onSeverityFilterChange={setSeverityFilter}
              onSortChange={setSortKey}
              onToggleConstraint={toggleConstraint}
            />
          </ResultPanel>
          <ResultPanel id="repairs" activeTab={activeTab}>
            <RepairsView state={analysisState} analysis={analysis} dataset={dataset} />
          </ResultPanel>
          <ResultPanel id="receipt" activeTab={activeTab}>
            <ReceiptView analysis={analysis} />
          </ResultPanel>
        </section>
      </main>
    </div>
  );
}

function BackendStatus({
  state,
  capability,
  onRetry,
}: {
  state: WorkState;
  capability: BackendCapability | null;
  onRetry: () => void;
}) {
  if (state === "loading") {
    return (
      <div className="status-pill status-pill--loading" role="status" aria-live="polite">
        <RefreshCw aria-hidden="true" />
        Warming backend
      </div>
    );
  }
  if (state === "error") {
    return (
      <button className="status-pill status-pill--error" type="button" onClick={onRetry}>
        <AlertTriangle aria-hidden="true" />
        Backend unavailable
      </button>
    );
  }
  return (
    <div className="status-pill status-pill--ready" role="status" aria-live="polite">
      <CheckCircle2 aria-hidden="true" />
      {capability?.advanced_available ? "Ready with advanced mode" : "Ready"}
    </div>
  );
}

function DatasetBadge({ dataset }: { dataset: DatasetInput | null }) {
  if (!dataset) {
    return <span className="muted-pill">Waiting</span>;
  }
  return (
    <span className="muted-pill">
      {dataset.preview.rows.length} preview rows, {dataset.preview.columns.length} columns
    </span>
  );
}

function CsvPreviewTable({ preview }: { preview: CsvPreview }) {
  return (
    <div className="table-frame" tabIndex={0} aria-label="CSV preview table">
      <table>
        <thead>
          <tr>
            {preview.columns.map((column) => (
              <th key={column} scope="col">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {preview.rows.map((row, index) => (
            <tr key={index}>
              {preview.columns.map((column) => (
                <td key={column}>{row[column]}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {preview.truncated ? <p className="table-note">Showing the first five parsed rows.</p> : null}
    </div>
  );
}

function ResultPanel({
  id,
  activeTab,
  children,
}: {
  id: TabId;
  activeTab: TabId;
  children: ReactNode;
}) {
  const active = id === activeTab;
  return (
    <div
      id={`panel-${id}`}
      role="tabpanel"
      aria-labelledby={`tab-${id}`}
      hidden={!active}
      tabIndex={active ? 0 : -1}
      className="tab-panel"
    >
      {children}
    </div>
  );
}

function RiskView({
  state,
  analysis,
  issues,
  filter,
  severityFilter,
  sortKey,
  selectedConstraintIds,
  onFilterChange,
  onSeverityFilterChange,
  onSortChange,
  onToggleConstraint,
}: {
  state: WorkState;
  analysis: AnalyzeResponse | null;
  issues: IssueGroup[];
  filter: string;
  severityFilter: Severity | "all";
  sortKey: SortKey;
  selectedConstraintIds: string[];
  onFilterChange: (value: string) => void;
  onSeverityFilterChange: (value: Severity | "all") => void;
  onSortChange: (value: SortKey) => void;
  onToggleConstraint: (candidateId: string, checked: boolean) => void;
}) {
  if (state === "loading") {
    return <LoadingState label="Analyzing CSV" />;
  }
  if (!analysis) {
    return (
      <EmptyState
        icon={<Activity aria-hidden="true" />}
        title="Analysis evidence appears here"
        body="Run Analyze to see risk, inferred constraints, verified repairs, and the dry-run receipt."
      />
    );
  }

  return (
    <div className="result-stack">
      <div className="metric-strip" aria-label="Risk summary">
        <Metric label="Rows" value={analysis.source.rows} />
        <Metric label="Columns" value={analysis.source.columns} />
        <Metric label="Issues" value={analysis.receipt.issues_count} />
        <Metric label="Pending repair constraints" value={analysis.risk_summary.pending_repair_supported_constraints} />
      </div>
      <RiskSummaryPanel
        datasetLevel={analysis.risk_summary.dataset_level}
        readiness={analysis.risk_summary.repair_readiness}
        reasons={analysis.risk_summary.reasons}
      />

      <div className="filter-row">
        <label>
          <span>Filter</span>
          <input
            type="search"
            value={filter}
            placeholder="Column or issue type"
            onChange={(event) => onFilterChange(event.target.value)}
          />
        </label>
        <label>
          <span>Severity</span>
          <select
            value={severityFilter}
            onChange={(event) => onSeverityFilterChange(event.target.value as Severity | "all")}
          >
            <option value="all">All severities</option>
            <option value="unsafe">Unsafe</option>
            <option value="review">Review</option>
            <option value="safe">Safe</option>
          </select>
        </label>
        <label>
          <span>Sort</span>
          <select value={sortKey} onChange={(event) => onSortChange(event.target.value as SortKey)}>
            <option value="severity">Severity</option>
            <option value="count">Count</option>
            <option value="column">Column</option>
          </select>
        </label>
      </div>

      {issues.length === 0 ? (
        <EmptyState
          icon={<ShieldCheck aria-hidden="true" />}
          title="No matching issues"
          body="Adjust the filters or analyze another dataset."
        />
      ) : (
        <IssueTable issues={issues} />
      )}

      <ConstraintReviewTable
        candidates={analysis.schema_inference.candidates}
        selectedConstraintIds={selectedConstraintIds}
        onToggleConstraint={onToggleConstraint}
      />
    </div>
  );
}

function RiskSummaryPanel({
  datasetLevel,
  readiness,
  reasons,
}: {
  datasetLevel: RiskLevel;
  readiness: RepairReadiness;
  reasons: string[];
}) {
  return (
    <div className="risk-panel">
      <div className="risk-badge-row">
        <RiskBadge label="Dataset risk" value={datasetLevel} />
        <RiskBadge label="Repair readiness" value={readiness} />
      </div>
      <ul className="risk-reasons" aria-label="Risk reasons">
        {reasons.map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>
    </div>
  );
}

function RiskBadge({ label, value }: { label: string; value: RiskLevel | RepairReadiness }) {
  return (
    <span className={`risk-badge risk-badge--${value}`}>
      <strong>{label}</strong>
      {formatLabel(value)}
    </span>
  );
}

function IssueTable({ issues }: { issues: IssueGroup[] }) {
  return (
    <div className="table-frame" tabIndex={0} aria-label="Grouped issue evidence">
      <table>
        <thead>
          <tr>
            <th scope="col">Column</th>
            <th scope="col">Issue type</th>
            <th scope="col">Severity</th>
            <th scope="col">Rows</th>
            <th scope="col">Count</th>
          </tr>
        </thead>
        <tbody>
          {issues.map((issue) => (
            <tr key={issue.key}>
              <td>
                <code>{issue.column}</code>
              </td>
              <td>{issue.issue_type}</td>
              <td>
                <SeverityBadge severity={issue.severity} />
              </td>
              <td>{formatRows(issue.row_indices, issue.row_indices_truncated)}</td>
              <td>{issue.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ConstraintReviewTable({
  candidates,
  selectedConstraintIds,
  onToggleConstraint,
}: {
  candidates: ConstraintCandidate[];
  selectedConstraintIds: string[];
  onToggleConstraint: (candidateId: string, checked: boolean) => void;
}) {
  const selected = new Set(selectedConstraintIds);
  const sortedCandidates = [...candidates].sort((a, b) => {
    if (a.repair_supported !== b.repair_supported) {
      return a.repair_supported ? -1 : 1;
    }
    if (a.decision !== b.decision) {
      return a.decision.localeCompare(b.decision);
    }
    return b.confidence - a.confidence;
  });

  return (
    <section className="result-stack" aria-labelledby="constraint-review-title">
      <div className="panel-heading panel-heading--tight">
        <div>
          <p className="eyebrow">Assumptions</p>
          <h3 id="constraint-review-title">Constraint review</h3>
        </div>
        <span className="muted-pill">{candidates.length} inferred</span>
      </div>
      {candidates.length === 0 ? (
        <EmptyState
          icon={<ShieldCheck aria-hidden="true" />}
          title="No inferred constraints"
          body="The schema inference pass did not emit reviewable candidates for this CSV."
        />
      ) : (
        <div className="table-frame" tabIndex={0} aria-label="Constraint review table">
          <table className="constraint-table">
            <thead>
              <tr>
                <th scope="col">Accept</th>
                <th scope="col">Kind</th>
                <th scope="col">Columns</th>
                <th scope="col">Confidence</th>
                <th scope="col">Decision</th>
                <th scope="col">Evidence</th>
              </tr>
            </thead>
            <tbody>
              {sortedCandidates.map((candidate) => (
                <tr key={candidate.candidate_id}>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`Accept ${candidate.kind} constraint ${candidate.candidate_id}`}
                      checked={selected.has(candidate.candidate_id)}
                      disabled={!candidate.repair_supported}
                      onChange={(event) =>
                        onToggleConstraint(candidate.candidate_id, event.target.checked)
                      }
                    />
                  </td>
                  <td>
                    <code>{formatLabel(candidate.kind)}</code>
                  </td>
                  <td>{formatConstraintColumns(candidate)}</td>
                  <td>{formatPercent(candidate.confidence)}</td>
                  <td>{candidate.repair_supported ? candidate.decision : "unsupported"}</td>
                  <td>{candidate.evidence}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function RepairsView({
  state,
  analysis,
  dataset,
}: {
  state: WorkState;
  analysis: AnalyzeResponse | null;
  dataset: DatasetInput | null;
}) {
  if (state === "loading") {
    return <LoadingState label="Verifying repair proposals" />;
  }
  if (!analysis) {
    return (
      <EmptyState
        icon={<Wrench aria-hidden="true" />}
        title="Verified repairs appear here"
        body={
          dataset
            ? "Run Analyze to inspect proposed changes, verifier evidence, and non-repairs."
            : "Load a sample or upload a CSV before requesting repair evidence."
        }
      />
    );
  }

  return (
    <div className="result-stack">
      <div className="metric-strip" aria-label="Verification summary">
        <Metric label="Safety" value={analysis.verification.safety_verdict} compact />
        <Metric label="Verifier" value={analysis.verification.verifier_verdict} compact />
        <Metric label="Verified fixes" value={analysis.repairs.length} />
        <Metric label="Attempted not fixed" value={analysis.verification.failures.length} />
      </div>
      <EvidenceNote
        title={analysis.repairs.length > 0 ? "Verified dry-run evidence" : "No verified repairs were proposed"}
        body={
          analysis.repairs.length > 0
            ? "Every listed fix passed the hosted safety and verifier gates."
            : "The dry-run pipeline did not find a candidate that passed safety and verifier gates."
        }
      />
      <ReceiptSummary analysis={analysis} />
      {analysis.repairs.length > 0 ? (
        <div className="repair-list">
          {analysis.repairs.map((fix) => (
            <RepairDiff key={`${fix.row}:${fix.column}:${fix.old_value}:${fix.new_value}`} fix={fix} analysis={analysis} />
          ))}
        </div>
      ) : null}
      <FailureList failures={analysis.verification.failures} />
    </div>
  );
}

function RepairDiff({ fix, analysis }: { fix: VerifiedFix; analysis: AnalyzeResponse }) {
  return (
    <article className="repair-row">
      <header>
        <div>
          <strong>
            Row {fix.row}, <code>{fix.column}</code>
          </strong>
          <small>
            {fix.detector_id} - confidence {Number(fix.confidence).toFixed(2)} - source {shortHash(analysis.source.sha256)}
          </small>
        </div>
        <span className="provenance-pill">{fix.provenance}</span>
      </header>
      <div className="diff-grid">
        <div className="diff-cell diff-cell--old">
          <span>Current</span>
          <code>{fix.old_value || "(empty)"}</code>
        </div>
        <div className="diff-cell diff-cell--new">
          <span>Proposed</span>
          <code>{fix.new_value || "(empty)"}</code>
        </div>
      </div>
      <p>{fix.reason}</p>
      {fix.verifier_reason ? <p className="verifier-note">{fix.verifier_reason}</p> : null}
    </article>
  );
}

function FailureList({ failures }: { failures: RepairFailure[] }) {
  if (failures.length === 0) {
    return null;
  }
  return (
    <section className="failure-list" aria-labelledby="failures-title">
      <h3 id="failures-title">Attempted but not fixed</h3>
      {failures.map((failure) => (
        <article
          className="failure-row"
          key={`${failure.row}:${failure.column}:${failure.issue_type}:${failure.reason}`}
        >
          <strong>
            Row {failure.row}, <code>{failure.column}</code>
          </strong>
          <span>{failure.issue_type} - {failure.status} - attempts {failure.attempt_count}</span>
          <p>{failure.reason}</p>
          {failure.unsat_core.length > 0 ? (
            <code>{failure.unsat_core.join(", ")}</code>
          ) : null}
        </article>
      ))}
    </section>
  );
}

function ReceiptView({ analysis }: { analysis: AnalyzeResponse | null }) {
  if (!analysis) {
    return (
      <EmptyState
        icon={<ShieldCheck aria-hidden="true" />}
        title="No receipt yet"
        body="A dry-run receipt and local apply handoff are shown after analysis completes."
      />
    );
  }
  return (
    <div className="result-stack">
      <ReceiptSummary analysis={analysis} />
      <ApplyHandoffPanel analysis={analysis} />
      <div className="journal-grid">
        <Metric label="Transaction" value={analysis.txn_journal.txn_id} compact />
        <Metric label="Fixes" value={analysis.txn_journal.fixes_count} />
        <Metric label="Applied" value={analysis.txn_journal.applied ? "yes" : "no"} />
        <Metric label="Source hash" value={shortHash(analysis.txn_journal.source_sha256)} compact />
        <pre tabIndex={0} aria-label="Dry-run transaction journal">
          {JSON.stringify(analysis.txn_journal, null, 2)}
        </pre>
        <pre tabIndex={0} aria-label="Repair receipt">
          {JSON.stringify(analysis.receipt, null, 2)}
        </pre>
      </div>
      <ul className="limitations" aria-label="Playground limitations">
        {analysis.limitations.map((limitation) => (
          <li key={limitation}>{limitation}</li>
        ))}
      </ul>
    </div>
  );
}

function ReceiptSummary({ analysis }: { analysis: AnalyzeResponse }) {
  return (
    <div className="receipt-grid" aria-label="Repair receipt summary">
      <Metric label="Safety" value={analysis.receipt.safety_verdict} compact />
      <Metric label="Verifier" value={analysis.receipt.verifier_verdict} compact />
      <Metric label="Accepted constraints" value={analysis.receipt.accepted_constraint_ids.length} />
      <Metric label="Reversible" value={analysis.receipt.reversible ? "yes" : "no"} />
      <p>{analysis.receipt.reason}</p>
    </div>
  );
}

function ApplyHandoffPanel({ analysis }: { analysis: AnalyzeResponse }) {
  return (
    <section className="handoff-panel" aria-labelledby="handoff-title">
      <div>
        <p className="eyebrow">Apply handoff</p>
        <h3 id="handoff-title">Local transaction boundary</h3>
      </div>
      <div className="command-list">
        <CommandRow label="Dry run" command={analysis.apply_handoff.dry_run_command} />
        <CommandRow label="Apply" command={analysis.apply_handoff.apply_command} />
        <CommandRow label="Audit" command={analysis.apply_handoff.audit_command} />
        <CommandRow label="Revert" command={analysis.apply_handoff.revert_command} />
      </div>
      <p>{analysis.apply_handoff.note}</p>
    </section>
  );
}

function CommandRow({ label, command }: { label: string; command: string }) {
  return (
    <div className="command-row">
      <span>{label}</span>
      <code>{command}</code>
    </div>
  );
}

function EvidenceNote({ title, body }: { title: string; body: string }) {
  return (
    <div className="evidence-note">
      <ShieldCheck aria-hidden="true" />
      <div>
        <strong>{title}</strong>
        <p>{body}</p>
      </div>
    </div>
  );
}

function CopyFallback({ evidenceText }: { evidenceText: string }) {
  return (
    <div className="copy-fallback" role="status" aria-live="polite">
      <strong>Clipboard permission was blocked</strong>
      <p>Export still works. You can also select this evidence payload directly.</p>
      <textarea aria-label="Copyable repair evidence" readOnly value={evidenceText} />
    </div>
  );
}

function Metric({
  label,
  value,
  compact = false,
}: {
  label: string;
  value: string | number;
  compact?: boolean;
}) {
  return (
    <div className={compact ? "metric metric--compact" : "metric"}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function SeverityBadge({ severity }: { severity: Severity }) {
  return <span className={`severity severity--${severity}`}>{severity}</span>;
}

function ProblemBanner({ problem }: { problem: ProblemDetail }) {
  return (
    <div className="problem-banner" role="alert">
      <AlertTriangle aria-hidden="true" />
      <div>
        <strong>{problem.title}</strong>
        <p>{problemToMessage(problem)}</p>
      </div>
    </div>
  );
}

function LoadingState({ label }: { label: string }) {
  return (
    <div className="loading-state" role="status" aria-live="polite">
      <RefreshCw aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

function EmptyState({
  icon,
  title,
  body,
}: {
  icon: ReactNode;
  title: string;
  body: string;
}) {
  return (
    <div className="empty-state">
      {icon}
      <strong>{title}</strong>
      <p>{body}</p>
    </div>
  );
}

function filterAndSortIssues(
  issues: IssueGroup[],
  filter: string,
  severity: Severity | "all",
  sortKey: SortKey,
) {
  const normalizedFilter = filter.trim().toLowerCase();
  const filtered = issues.filter((issue) => {
    const matchesSeverity = severity === "all" || issue.severity === severity;
    const matchesFilter =
      normalizedFilter.length === 0 ||
      issue.column.toLowerCase().includes(normalizedFilter) ||
      issue.issue_type.toLowerCase().includes(normalizedFilter);
    return matchesSeverity && matchesFilter;
  });

  return [...filtered].sort((a, b) => {
    if (sortKey === "column") {
      return a.column.localeCompare(b.column);
    }
    if (sortKey === "count") {
      return b.count - a.count;
    }
    return groupIssues([a, b])[0].key === a.key ? -1 : 1;
  });
}

function formatConstraintColumns(candidate: ConstraintCandidate): string {
  const left = candidate.columns.join(", ");
  return candidate.dependent ? `${left} -> ${candidate.dependent}` : left;
}

function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function formatLabel(value: string): string {
  return value.replace(/_/g, " ");
}

function shortHash(value: string): string {
  return value.slice(0, 12);
}

function problemFromUnknown(error: unknown): ProblemDetail {
  if (error instanceof ApiProblemError) {
    return error.problem;
  }
  return localProblem(error instanceof Error ? error.message : "The request failed.");
}

function localProblem(message: string): ProblemDetail {
  return {
    type: "https://dataforge.local/problems/frontend_validation",
    title: "Dataset validation failed",
    status: 400,
    detail: message,
    error: "frontend_validation",
  };
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export default App;
