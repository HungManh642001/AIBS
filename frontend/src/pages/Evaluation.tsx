import { useState, useEffect } from "react";
import { Button, Collapse, Input, Select, Table, Tag, Tooltip, message } from "antd";
import { DownloadOutlined } from "@ant-design/icons";
import { useParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import type { CriterionEval, EvalResultsPayload, Verdict, VendorEval } from "../api/types";

const KQ_OPTS = [
  { value: "đạt", label: "Đạt" },
  { value: "không đạt", label: "Không đạt" },
  { value: "cần làm rõ", label: "Cần làm rõ" },
];

function pillClass(kq: string): string {
  if (kq === "đạt") return "PASS";
  if (kq === "không đạt") return "FAIL";
  if (kq === "lỗi") return "ERROR";
  return "PARTIAL"; // cần làm rõ | thiếu hồ sơ
}

function ResultPill({ kq }: { kq: string }) {
  const label = kq === "lỗi" ? "AI LỖI" : kq.toUpperCase();
  return <span className={`verdict-result-pill ${pillClass(kq)}`}>{label}</span>;
}

function VerdictTable({ verdicts, onOverride }: {
  verdicts: Verdict[];
  onOverride: (id: number, payload: Record<string, unknown>) => void;
}) {
  return (
    <Table<Verdict>
      rowKey="id"
      dataSource={verdicts}
      pagination={false}
      size="small"
      scroll={{ x: 1100 }}
      columns={[
        {
          title: "Nội dung kiểm tra", width: 240,
          render: (_, v) => (
            <div>
              <div style={{ fontWeight: 600 }}>{v.noi_dung_kiem_tra}</div>
              <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>HSDT: {v.hsdt_kiem_tra}</div>
            </div>
          ),
        },
        { title: "Chuẩn HSMT", dataIndex: "thong_tin_bo_sung", width: 200,
          render: (t) => t || <span style={{ color: "var(--ink-muted)" }}>—</span> },
        {
          title: "Kết quả", width: 190,
          render: (_, v) => (
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <Select
                size="small" style={{ width: 130 }} value={v.ket_qua} options={KQ_OPTS}
                onChange={(kq) => onOverride(v.id, { ket_qua: kq })}
              />
              {v.overridden && <Tag color="blue">đã sửa</Tag>}
            </div>
          ),
        },
        {
          title: "Bằng chứng (HSDT)", width: 260,
          render: (_, v) => (
            <div>
              <div>{v.bang_chung || <span style={{ color: "var(--ink-muted)" }}>—</span>}</div>
              {v.trang?.length > 0 && (
                <div className="mono" style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                  [trang {v.trang.join(", ")}]
                </div>
              )}
            </div>
          ),
        },
        { title: "Độ tin", dataIndex: "do_tin", width: 70,
          render: (d: number) => <span className="mono">{d.toFixed(2)}</span> },
        {
          title: "Ghi chú", width: 200,
          render: (_, v) => (
            <Input.TextArea
              size="small" autoSize={{ minRows: 1, maxRows: 4 }} defaultValue={v.ghi_chu}
              onBlur={(e) => {
                if (e.target.value !== v.ghi_chu) onOverride(v.id, { ghi_chu: e.target.value });
              }}
            />
          ),
        },
      ]}
    />
  );
}

function SummaryChips({ v }: { v: VendorEval }) {
  const s = v.summary;
  return (
    <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
      <Tag>{s.n_tieu_chi} tiêu chí</Tag>
      <Tag color="green">{s.n_dat} đạt</Tag>
      <Tag color="red">{s.n_khong_dat} không đạt</Tag>
      <Tag color="orange">{s.n_can_lam_ro} cần làm rõ</Tag>
      {s.n_loai > 0 && <Tag color="volcano">⛔ {s.n_loai} tiêu chí loại</Tag>}
    </div>
  );
}

function VendorSection({ v, onOverride }: {
  v: VendorEval;
  onOverride: (id: number, payload: Record<string, unknown>) => void;
}) {
  const biLoai = v.criteria.some((c) => c.loai);
  return (
    <div style={{ background: "var(--paper)", border: "1px solid var(--line)", borderRadius: 8,
                  overflow: "hidden", marginBottom: 20 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 16, padding: "16px 20px",
                    borderBottom: "1px solid var(--line)", background: "var(--surface)" }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.06em",
                        textTransform: "uppercase", color: "var(--ink-muted)", marginBottom: 2 }}>
            Nhà thầu
          </div>
          <div style={{ fontSize: 16, fontWeight: 700, color: "var(--ink)" }}>
            {v.ten} {biLoai && <Tag color="volcano" style={{ marginLeft: 8 }}>Bị loại (tiên quyết)</Tag>}
          </div>
        </div>
        <SummaryChips v={v} />
      </div>

      <div style={{ padding: "12px 16px 16px" }}>
        {v.criteria.length === 0 ? (
          <div style={{ textAlign: "center", padding: "24px 0", color: "var(--ink-muted)", fontSize: 13 }}>
            Chưa có kết quả đánh giá
          </div>
        ) : (
          <Collapse
            items={v.criteria.map((c: CriterionEval) => ({
              key: String(c.eval_id),
              label: (
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <ResultPill kq={c.ket_qua} />
                  <span style={{ fontWeight: 600 }}>{c.ten}</span>
                  {c.tien_quyet && <Tag>tiên quyết</Tag>}
                  {c.loai && <Tag color="volcano">⛔ LOẠI</Tag>}
                </div>
              ),
              children: <VerdictTable verdicts={c.verdicts} onOverride={onOverride} />,
            }))}
          />
        )}
      </div>
    </div>
  );
}

export default function Evaluation() {
  const { id } = useParams();
  const [data, setData] = useState<EvalResultsPayload | null>(null);

  const load = () =>
    api.get(`/packages/${id}/results`)
      .then((r) => setData(unwrap<EvalResultsPayload>(r)))
      .catch(() => {});

  useEffect(() => { load(); }, [id]);

  const onOverride = async (verdictId: number, payload: Record<string, unknown>) => {
    try {
      await api.put(`/evaluation/verdict/${verdictId}/override`, payload);
      message.success("Đã cập nhật");
      load();
    } catch (e: any) { message.error(e.message); }
  };

  const genReport = async (loai: "word" | "excel") => {
    try {
      const res = unwrap<{ report_id: number }>(await api.post(`/packages/${id}/reports?loai=${loai}`));
      window.open(`http://localhost:8000/api/v1/reports/${res.report_id}/download`, "_blank");
    } catch (e: any) { message.error(e.message); }
  };

  if (!data) return null;

  const hasError = data.vendors.some((v) =>
    v.criteria.some((c) => c.verdicts.some((s) => s.ket_qua === "lỗi" && !s.overridden)));

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 20 }}>
        <div>
          <span className="page-eyebrow">Kết quả đánh giá</span>
          <h1 className="page-title" style={{ marginBottom: 0 }}>Phán quyết có dẫn chứng</h1>
        </div>
        <Tooltip title={hasError ? "Còn verdict AI lỗi — hãy xử lý trước khi xuất" : ""}>
          <span style={{ display: "inline-flex", gap: 8 }}>
            <Button icon={<DownloadOutlined />} disabled={hasError} onClick={() => genReport("word")}>Xuất Word</Button>
            <Button icon={<DownloadOutlined />} disabled={hasError} onClick={() => genReport("excel")}>Xuất Excel</Button>
          </span>
        </Tooltip>
      </div>

      {data.vendors.length === 0 ? (
        <div style={{ textAlign: "center", padding: "60px 0", background: "var(--paper)",
                      border: "1px solid var(--line)", borderRadius: 8, color: "var(--ink-muted)", fontSize: 14 }}>
          Chưa có kết quả. Hãy chạy đánh giá trước.
        </div>
      ) : (
        data.vendors.map((v: VendorEval) => (
          <VendorSection key={v.vendor_id} v={v} onOverride={onOverride} />
        ))
      )}
    </div>
  );
}
