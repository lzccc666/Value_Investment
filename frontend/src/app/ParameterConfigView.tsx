import {
  AlertTriangle,
  CheckCircle2,
  RotateCcw,
  Search,
  SlidersHorizontal,
  Upload
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  getCurrentParameterConfig,
  getDefaultParameterConfig,
  publishParameterConfig,
  validateParameterConfig,
  type ParameterConfigCurrentResponse,
  type ParameterMetadataItem,
  type ParameterValidationResult
} from "../services/api";
import {
  calculationRoleLabel,
  matrixCoefficientDescription,
  matrixParameterLabel,
  parameterRiskLabel,
  parameterValueLabel,
  parameterValueOptions
} from "./parameterConfigLabels";

type ParameterConfigViewProps = { refreshToken: number };

const DOMAIN_LABELS: Record<string, string> = {
  data_sampling: "数据采样",
  financial_flags: "财务预警",
  analyst_engine: "分析师引擎",
  valuation_rule_matrix: "规则矩阵",
  memo_decision: "备忘录决策",
  valuation_models: "估值模型",
  price_decision: "价格决策"
};

const DOMAINS = Object.keys(DOMAIN_LABELS);

export function ParameterConfigView({ refreshToken }: ParameterConfigViewProps) {
  const [current, setCurrent] = useState<ParameterConfigCurrentResponse | null>(null);
  const [defaults, setDefaults] = useState<ParameterConfigCurrentResponse | null>(null);
  const [config, setConfig] = useState<Record<string, unknown>>({});
  const [activeDomain, setActiveDomain] = useState("data_sampling");
  const [validation, setValidation] = useState<ParameterValidationResult | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [publishReady, setPublishReady] = useState(false);
  const [warningsAcknowledged, setWarningsAcknowledged] = useState(false);
  const [matrixAnalyst, setMatrixAnalyst] = useState("");
  const [matrixRule, setMatrixRule] = useState("");
  const [matrixDimension, setMatrixDimension] = useState("");

  const load = useCallback(async (signal?: AbortSignal) => {
    setBusy(true);
    try {
      const [nextCurrent, nextDefaults] = await Promise.all([
        getCurrentParameterConfig(signal),
        getDefaultParameterConfig(signal)
      ]);
      setCurrent(nextCurrent);
      setDefaults(nextDefaults);
      setConfig(structuredClone(nextCurrent.config_json));
      setValidation(nextCurrent.validation);
      setPublishReady(false);
      setWarningsAcknowledged(false);
      setMessage(nextCurrent.source === "builtin_fallback" ? "源码参数文件无效，当前已整体使用内置默认值。" : "");
    } catch (error) {
      if (!signal?.aborted) setMessage(errorMessage(error));
    } finally {
      if (!signal?.aborted) setBusy(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load, refreshToken]);

  const changedPaths = useMemo(
    () => changedLeafPaths(current?.config_json ?? {}, config),
    [config, current]
  );

  const domainMetadata = useMemo(() => {
    if (!current) return [];
    return current.metadata.filter(
      (item) => item.domain === activeDomain && !item.path.includes(".rule_mappings.")
    );
  }, [activeDomain, current]);

  async function validateConfig() {
    setBusy(true);
    try {
      const result = await validateParameterConfig(config);
      setValidation(result);
      setPublishReady(result.valid);
      setWarningsAcknowledged(false);
      setMessage(result.valid ? "校验通过。确认发布后才会写入源码参数文件。" : `发现 ${result.errors.length} 个严重错误`);
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function publishConfig() {
    if (!validation?.valid) return;
    setBusy(true);
    try {
      await publishParameterConfig(config, warningsAcknowledged);
      await load();
      setMessage("已发布并直接更新源码参数；后续新分析将使用这组参数。");
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  function updateValue(path: string, value: unknown) {
    setConfig((previous) => setNestedValue(previous, path.split("."), value));
    setValidation(null);
    setPublishReady(false);
  }

  function updateRuleMapping(ruleKey: string, name: string, value: number) {
    setConfig((previous) => {
      const clone = structuredClone(previous);
      const matrix = clone.valuation_rule_matrix as Record<string, unknown>;
      const mappings = matrix.rule_mappings as Record<string, RuleMapping>;
      mappings[ruleKey].dimensions[name] = value;
      return clone;
    });
    setValidation(null);
    setPublishReady(false);
  }

  function restoreDomain() {
    if (!defaults) return;
    setConfig((previous) => ({
      ...previous,
      [activeDomain]: structuredClone(defaults.config_json[activeDomain])
    }));
    setValidation(null);
    setPublishReady(false);
  }

  if (!current || !defaults) {
    return <div className="parameter-config-view"><p className="config-message">{message || "正在读取参数配置"}</p></div>;
  }

  return (
    <div className="parameter-config-view">
      <div className="config-toolbar">
        <div className="config-version-block">
          <strong>{current.source === "source_file" ? "当前源码参数" : "当前内置默认参数"}</strong>
          <span>{current.config_hash.slice(0, 12)} · {current.validation.actual_parameter_count} 个生效参数</span>
        </div>
        <div className="config-actions">
          <button className="icon-command" type="button" title="校验当前页面参数" disabled={busy} onClick={() => void validateConfig()}><CheckCircle2 size={17} /><span>校验</span></button>
        </div>
      </div>

      {message ? <p className="config-message" role="status">{message}</p> : null}

      <div className="config-tabs" role="tablist" aria-label="配置域">
        {DOMAINS.map((domain) => (
          <button key={domain} type="button" role="tab" aria-selected={activeDomain === domain} className={activeDomain === domain ? "is-active" : ""} onClick={() => setActiveDomain(domain)}>
            {DOMAIN_LABELS[domain]}
          </button>
        ))}
      </div>

      <section className="config-domain" aria-labelledby="config-domain-heading">
        <div className="config-domain-heading">
          <div><SlidersHorizontal size={19} /><h2 id="config-domain-heading">{DOMAIN_LABELS[activeDomain]}</h2></div>
          <button className="icon-command" type="button" onClick={restoreDomain} title="恢复当前分组默认值"><RotateCcw size={16} /><span>恢复分组</span></button>
        </div>

        <div className="parameter-grid">
          {domainMetadata.map((item) => (
            <ParameterField
              key={item.path}
              item={item}
              value={getNestedValue(config, item.path.split("."))}
              onChange={(value) => updateValue(item.path, value)}
              onRestore={() => updateValue(item.path, item.default_value)}
            />
          ))}
          {domainMetadata.length === 0 && activeDomain !== "valuation_rule_matrix" ? <p className="config-empty">该分组没有可编辑参数。</p> : null}
        </div>
        {activeDomain === "valuation_rule_matrix" ? (
          <RuleMatrixEditor
            config={config}
            analyst={matrixAnalyst}
            ruleQuery={matrixRule}
            dimension={matrixDimension}
            onAnalyst={setMatrixAnalyst}
            onRuleQuery={setMatrixRule}
            onDimension={setMatrixDimension}
            onChange={updateRuleMapping}
          />
        ) : null}
      </section>

      <section className="config-release-band">
        <div className="config-release-copy">
          <strong>未发布修改只保留在当前页面</strong>
          <span>发布才会覆盖源码参数文件；关闭或刷新页面不会留下记录，也不会应用修改。</span>
        </div>
        <div className="config-change-summary"><strong>{changedPaths.length}</strong><span>项待发布</span></div>
        <button className="primary-command" type="button" disabled={busy || changedPaths.length === 0} onClick={() => void validateConfig()}><Upload size={17} />校验并准备发布</button>
      </section>

      {validation ? <ValidationPanel validation={validation} metadata={current.metadata} /> : null}

      {publishReady ? (
        <section className="publish-confirmation" aria-label="发布确认">
          <div><strong>确认覆盖源码参数</strong><span>本次发布仅影响后续新分析；已有运行继续使用各自保存的参数快照。</span></div>
          {validation?.warnings.length ? (
            <label><input type="checkbox" checked={warningsAcknowledged} onChange={(event) => setWarningsAcknowledged(event.target.checked)} />我已复核 {validation.warnings.length} 条警告</label>
          ) : null}
          <button className="primary-command" type="button" disabled={busy || Boolean(validation?.warnings.length && !warningsAcknowledged)} onClick={() => void publishConfig()}><Upload size={17} />确认发布</button>
        </section>
      ) : null}
    </div>
  );
}

function ParameterField({ item, value, onChange, onRestore }: { item: ParameterMetadataItem; value: unknown; onChange: (value: unknown) => void; onRestore: () => void }) {
  const isPercent = item.unit === "%" && typeof value === "number";
  const displayed = typeof value === "number" ? formatEditableNumber(value, isPercent) : String(value ?? "");
  const valueOptions = typeof value === "string" ? parameterValueOptions(item.path) : [];
  return (
    <label className="parameter-field" title={item.description}>
      <span className="parameter-label"><strong>{item.label}</strong></span>
      <span className="parameter-description">{item.description}</span>
      <div className="parameter-input-row">
        {typeof value === "boolean" ? (
          <input type="checkbox" checked={value} onChange={(event) => onChange(event.target.checked)} />
        ) : typeof value === "number" ? (
          <input type="number" value={displayed} step={isPercent ? "0.1" : "any"} onChange={(event) => onChange(isPercent ? Number(event.target.value) / 100 : Number(event.target.value))} />
        ) : valueOptions.length > 0 ? (
          <select value={String(value)} onChange={(event) => onChange(event.target.value)}>
            {valueOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        ) : (
          <input value={String(value ?? "")} onChange={(event) => onChange(event.target.value)} />
        )}
        <span>{item.unit}</span>
        <button type="button" title="恢复此项默认值" onClick={(event) => { event.preventDefault(); onRestore(); }}><RotateCcw size={14} /></button>
      </div>
      <small>默认 {formatValue(item.default_value, item.unit)} · 风险 {parameterRiskLabel(item.risk)}</small>
    </label>
  );
}

function RuleMatrixEditor({ config, analyst, ruleQuery, dimension, onAnalyst, onRuleQuery, onDimension, onChange }: { config: Record<string, unknown>; analyst: string; ruleQuery: string; dimension: string; onAnalyst: (value: string) => void; onRuleQuery: (value: string) => void; onDimension: (value: string) => void; onChange: (ruleKey: string, name: string, value: number) => void }) {
  const mappings = ((((config.valuation_rule_matrix as Record<string, unknown>)?.rule_mappings) ?? {}) as Record<string, RuleMapping>);
  const rows = Object.entries(mappings);
  const analysts = [...new Map(rows.map(([, row]) => [row.profile_id, row.profile_name])).entries()];
  const dimensions = [...new Set(rows.flatMap(([, row]) => Object.keys(row.dimensions)))];
  const filtered = rows.filter(([, row]) => (!analyst || row.profile_id === analyst) && (!ruleQuery || `${row.rule_id}${row.rule_label}`.toLowerCase().includes(ruleQuery.toLowerCase())) && (!dimension || dimension in row.dimensions));
  return (
    <div className="rule-matrix-editor">
      <div className="matrix-filters">
        <label><span>分析师</span><select value={analyst} onChange={(event) => onAnalyst(event.target.value)}><option value="">全部</option>{analysts.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label><span>规则</span><Search size={15} /><input value={ruleQuery} onChange={(event) => onRuleQuery(event.target.value)} placeholder="输入规则名称" /></label>
        <label><span>维度</span><select value={dimension} onChange={(event) => onDimension(event.target.value)}><option value="">全部</option>{dimensions.map((value) => <option key={value} value={value}>{matrixParameterLabel(value)}</option>)}</select></label>
        <strong>{filtered.length} / 40</strong>
      </div>
      <div className="matrix-table-wrap">
        <table className="matrix-table"><thead><tr><th>分析师 / 规则</th><th>计算角色</th><th>实际计算维度</th></tr></thead><tbody>
          {filtered.map(([key, row]) => <tr key={key}>
            <td><span className="matrix-mobile-label">分析师 / 规则</span><strong>{row.profile_name}</strong><span>{row.rule_label}</span></td>
            <td><span className="matrix-mobile-label">计算角色</span><span className={`config-status config-status--${row.calculation_role === "compute" ? "published" : "archived"}`}>{calculationRoleLabel(row.calculation_role)}</span></td>
            <td><span className="matrix-mobile-label">实际计算维度</span><CoefficientInputs row={row} onChange={(name, value) => onChange(key, name, value)} /></td>
          </tr>)}
        </tbody></table>
      </div>
    </div>
  );
}

type RuleMapping = { profile_id: string; profile_name: string; rule_id: string; rule_label: string; calculation_role: string; dimensions: Record<string, number> };

function CoefficientInputs({ row, onChange }: { row: RuleMapping; onChange: (name: string, value: number) => void }) {
  return <div className="coefficient-list">{Object.entries(row.dimensions).map(([name, value]) => {
    const description = matrixCoefficientDescription(row.profile_name, row.rule_label, name, value, row.calculation_role);
    return <label key={name} title={description}><span>{matrixParameterLabel(name)}</span><input aria-label={`${row.profile_name}${row.rule_label}${matrixParameterLabel(name)}系数`} type="number" step="0.05" value={formatEditableNumber(value)} disabled={row.calculation_role !== "compute"} onChange={(event) => onChange(name, Number(event.target.value))} /></label>;
  })}</div>;
}

function ValidationPanel({ validation, metadata }: { validation: ParameterValidationResult; metadata: ParameterMetadataItem[] }) {
  const issues = [...validation.errors, ...validation.warnings];
  return <section className={`validation-panel ${validation.valid ? "validation-panel--valid" : "validation-panel--invalid"}`}><div><CheckCircle2 size={18} /><strong>{validation.valid ? "配置校验通过" : `${validation.errors.length} 个严重错误`}</strong><span>{validation.warnings.length} 条警告</span></div>{issues.length ? <ul>{issues.map((issue, index) => <li key={`${issue.path}-${issue.code}-${index}`}><AlertTriangle size={15} /><span className="validation-parameter-name">{validationIssueLabel(issue.path, metadata)}</span><span>{issue.message}</span></li>)}</ul> : null}</section>;
}

function getNestedValue(value: unknown, path: string[]): unknown { let current = value; for (const key of path) { if (!current || typeof current !== "object") return undefined; current = (current as Record<string, unknown>)[key]; } return current; }
function setNestedValue(source: Record<string, unknown>, path: string[], value: unknown): Record<string, unknown> { const clone = structuredClone(source); let current: Record<string, unknown> = clone; for (const key of path.slice(0, -1)) { current = current[key] as Record<string, unknown>; } current[path[path.length - 1]] = value; return clone; }
function changedLeafPaths(left: unknown, right: unknown, path = ""): string[] { if (left && right && typeof left === "object" && typeof right === "object" && !Array.isArray(left) && !Array.isArray(right)) { const keys = new Set([...Object.keys(left as object), ...Object.keys(right as object)]); return [...keys].flatMap((key) => changedLeafPaths((left as Record<string, unknown>)[key], (right as Record<string, unknown>)[key], path ? `${path}.${key}` : key)); } if (Array.isArray(left) && Array.isArray(right)) return left.length === right.length && left.every((item, index) => Object.is(item, right[index])) ? [] : [path]; return Object.is(left, right) ? [] : [path]; }
function formatEditableNumber(value: number, isPercent = false): string {
  const scaled = isPercent ? value * 100 : value;
  return String(Number(scaled.toFixed(10)));
}
function formatValue(value: unknown, unit: string): string { if (typeof value === "number") return `${formatEditableNumber(value, unit === "%")}${unit === "%" ? "%" : ""}`; if (typeof value === "string") return parameterValueLabel(value); return String(value ?? "-"); }
function errorMessage(error: unknown): string { return error instanceof Error ? error.message : "参数配置操作失败"; }
function validationIssueLabel(path: string, metadata: ParameterMetadataItem[]): string { if (!path) return "全局配置"; if (path.includes("rule_mappings")) return "规则矩阵"; return metadata.find((item) => item.path === path)?.label ?? "参数配置"; }
