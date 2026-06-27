import { useState, useEffect } from "react";
import { Button, message, Tooltip } from "antd";
import { DownloadOutlined, CaretDownOutlined, CaretRightOutlined } from "@ant-design/icons";
import { useParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import type { ResultsBreakdown, VendorBreakdown, CriteriaBreakdown } from "../api/types";
import SubCheckTable from "../components/SubCheckTable";

function ResultPill({ result }: { result: string | null }) {
  const v = result ?? "—";
  const cls = ["PASS", "FAIL", "PARTIAL", "ERROR"].includes(v) ? v : "default";
  const label = v === "ERROR" ? "AI LỖI" : v;
  return <span className={`verdict-result-pill ${cls}`}>{label}</span>;
}

function CompletenessBar({ percent, missing }: { percent: number; missing: string[] }) {
  const color = percent === 100 ? "var(--pass)" : percent >= 70 ? "var(--partial)" : "var(--fail)";
  return (
    <Tooltip title={missing.length ? `Thiếu: ${missing.join(", ")}` : "Đủ tài liệu"}>
      <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
        <span className="completeness-bar-track" style={{ margin: 0 }}>
          <span className="completeness-bar-fill" style={{ width: `${percent}%`, background: color }} />
        </span>
        <span className="mono" style={{ fontSize: 12, color: "var(--ink-muted)" }}>{percent}%</span>
      </span>
    </Tooltip>
  );
}

function CriteriaCard({ c, onChanged }: { c: CriteriaBreakdown; onChanged: () => void }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="verdict-card">
      <div
        className="verdict-header"
        onClick={() => setOpen((p) => !p)}
        style={{ borderBottom: open ? "1px solid var(--line)" : "none" }}
      >
        <ResultPill result={c.result} />
        <span className="verdict-ten">{c.criteria_ten}</span>
        <span className="verdict-score">
          {c.score > 0 ? `${c.score} điểm` : ""}
        </span>
        <span style={{ color: "var(--ink-muted)", marginLeft: 4 }}>
          {open ? <CaretDownOutlined /> : <CaretRightOutlined />}
        </span>
      </div>

      {open && (
        <div style={{ padding: "0 0 4px" }}>
          <SubCheckTable subs={c.sub_results} onChanged={onChanged} />
        </div>
      )}
    </div>
  );
}

function VendorSection({ v, onChanged }: { v: VendorBreakdown; onChanged: () => void }) {
  const passCount  = v.criteria.filter((c) => c.result === "PASS").length;
  const failCount  = v.criteria.filter((c) => c.result === "FAIL").length;
  const totalCount = v.criteria.length;
  const overallResult = failCount > 0 ? "FAIL" : passCount === totalCount ? "PASS" : totalCount > 0 ? "PARTIAL" : null;

  return (
    <div style={{
      background: "var(--paper)",
      border: "1px solid var(--line)",
      borderRadius: 8,
      overflow: "hidden",
      marginBottom: 20,
    }}>
      {/* Vendor header */}
      <div style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "16px 20px",
        borderBottom: "1px solid var(--line)",
        background: "var(--surface)",
      }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--ink-muted)", marginBottom: 2 }}>
            Nhà thầu
          </div>
          <div style={{ fontSize: 16, fontWeight: 700, color: "var(--ink)" }}>{v.ten}</div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 11, color: "var(--ink-muted)", fontWeight: 500, marginBottom: 2 }}>Hồ sơ</div>
            <CompletenessBar percent={v.completeness.percent} missing={v.completeness.missing} />
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 11, color: "var(--ink-muted)", fontWeight: 500, marginBottom: 4 }}>Phán quyết</div>
            {overallResult && <ResultPill result={overallResult} />}
          </div>
        </div>
      </div>

      {/* Criteria list */}
      <div style={{ padding: "12px 16px 16px" }}>
        {v.criteria.length === 0 ? (
          <div style={{ textAlign: "center", padding: "24px 0", color: "var(--ink-muted)", fontSize: 13 }}>
            Chưa có kết quả đánh giá
          </div>
        ) : (
          v.criteria.map((c: CriteriaBreakdown) => (
            <CriteriaCard key={c.criteria_id} c={c} onChanged={onChanged} />
          ))
        )}
      </div>
    </div>
  );
}

export default function Evaluation() {
  const { id } = useParams();
  const [data, setData] = useState<ResultsBreakdown | null>(null);

  const load = () =>
    api.get(`/packages/${id}/results`)
      .then((r) => setData(unwrap<ResultsBreakdown>(r)))
      .catch(() => {});

  useEffect(() => { load(); }, [id]);

  const genReport = async (loai: "word" | "excel") => {
    try {
      const res = unwrap<{ report_id: number }>(
        await api.post(`/packages/${id}/reports?loai=${loai}`)
      );
      window.open(`http://localhost:8000/api/v1/reports/${res.report_id}/download`, "_blank");
    } catch (e: any) {
      message.error(e.message);
    }
  };

  if (!data) return null;

  const hasError = data.vendors.some((v) =>
    v.criteria.some((c) =>
      c.result === "ERROR" ||
      c.sub_results.some((s) => s.result === "ERROR" && !s.overridden)
    )
  );

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 20 }}>
        <div>
          <span className="page-eyebrow">Kết quả đánh giá</span>
          <h1 className="page-title" style={{ marginBottom: 0 }}>Phán quyết có dẫn chứng</h1>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Tooltip title={hasError ? "Còn điểm kiểm AI lỗi — hãy xử lý trước khi xuất" : ""}>
            <span style={{ display: "inline-flex", gap: 8 }}>
              <Button icon={<DownloadOutlined />} disabled={hasError} onClick={() => genReport("word")}>Xuất Word</Button>
              <Button icon={<DownloadOutlined />} disabled={hasError} onClick={() => genReport("excel")}>Xuất Excel</Button>
            </span>
          </Tooltip>
        </div>
      </div>

      {data.vendors.length === 0 ? (
        <div style={{
          textAlign: "center", padding: "60px 0",
          background: "var(--paper)", border: "1px solid var(--line)", borderRadius: 8,
          color: "var(--ink-muted)", fontSize: 14,
        }}>
          Chưa có kết quả. Hãy chạy đánh giá trước.
        </div>
      ) : (
        data.vendors.map((v: VendorBreakdown) => (
          <VendorSection key={v.vendor_id} v={v} onChanged={load} />
        ))
      )}
    </div>
  );
}
