import { useState, useEffect } from "react";
import { Badge, Button, Collapse, Input, Select, Table, Tabs, Tag, Tooltip, message } from "antd";
import { ArrowLeftOutlined, DownloadOutlined } from "@ant-design/icons";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import type { CriterionEval, EvalResultsPayload, Verdict, VendorEval } from "../api/types";
import Loader from "../components/Loader";

const KQ_OPTS = [
  { value: "đạt", label: "Đạt" },
  { value: "không đạt", label: "Không đạt" },
  { value: "cần làm rõ", label: "Cần làm rõ" },
  { value: "không áp dụng", label: "Không áp dụng" },
];

function pillClass(kq: string): string {
  if (kq === "đạt") return "PASS";
  if (kq === "không đạt") return "FAIL";
  if (kq === "lỗi") return "ERROR";
  if (kq === "không áp dụng") return "default"; // trung tính (xám) — khác cam "cần làm rõ"
  return "PARTIAL"; // cần làm rõ | thiếu hồ sơ
}

function ResultPill({ kq }: { kq: string }) {
  const label = kq === "lỗi" ? "AI LỖI" : kq.toUpperCase();
  return <span className={`verdict-result-pill ${pillClass(kq)}`}>{label}</span>;
}

// Bản đồ loại hồ sơ -> file, để hiện bằng chứng dạng "don_du_thau (don.pdf) tr.3" (truy vết được).
function filesOf(v: VendorEval): Record<string, string[]> {
  const m: Record<string, string[]> = {};
  (v.ho_so_nhan_duoc ?? []).forEach((h) => { m[h.loai_ho_so] = h.files; });
  return m;
}

function nguonHsdt(vd: Verdict, files: Record<string, string[]>): string {
  const loais = vd.nguon_doc && vd.nguon_doc.length > 0 ? vd.nguon_doc : [vd.hsdt_kiem_tra];
  const parts = loais.filter(Boolean).map((t) => {
    const fs = files[t];
    return fs && fs.length ? `${t} (${fs.join(", ")})` : t;
  });
  const tr = vd.trang?.length ? `tr.${vd.trang.join(",")}` : "tr.(không nêu)";
  return `${parts.join("; ")} ${tr}`;
}

function VerdictTable({ verdicts, files, onOverride }: {
  verdicts: Verdict[];
  files: Record<string, string[]>;
  onOverride: (id: number, payload: Record<string, unknown>) => void;
}) {
  return (
    <Table<Verdict>
      rowKey="id"
      dataSource={verdicts}
      pagination={false}
      size="small"
      scroll={{ x: 1240 }}
      columns={[
        {
          title: "Nội dung kiểm tra", width: 220,
          render: (_, v) => (
            <div>
              <div style={{ fontWeight: 600 }}>{v.noi_dung_kiem_tra}</div>
              <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>HSDT: {v.hsdt_kiem_tra}</div>
            </div>
          ),
        },
        {
          title: "Chuẩn HSMT", width: 210,
          render: (_, v) => (
            <div>
              <div>{v.thong_tin_bo_sung || <span style={{ color: "var(--ink-muted)" }}>—</span>}</div>
              {v.nguon_hsmt && (
                <div className="mono" style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                  điều khoản: {v.nguon_hsmt}
                </div>
              )}
            </div>
          ),
        },
        {
          title: "Kết quả", width: 190,
          render: (_, v) => (
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <Select
                size="small" style={{ width: 140 }} value={v.ket_qua} options={KQ_OPTS}
                onChange={(kq) => onOverride(v.id, { ket_qua: kq })}
              />
              {v.overridden && <Tag color="blue">đã sửa</Tag>}
            </div>
          ),
        },
        {
          title: "Bằng chứng (HSDT)", width: 280,
          render: (_, v) => (
            <div>
              <div>{v.bang_chung || <span style={{ color: "var(--ink-muted)" }}>—</span>}</div>
              <div className="mono" style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                {nguonHsdt(v, files)}
              </div>
            </div>
          ),
        },
        { title: "Độ tin", dataIndex: "do_tin", width: 66,
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
      {(s.n_khong_ap_dung ?? 0) > 0 && <Tag>{s.n_khong_ap_dung} không áp dụng</Tag>}
      {s.n_loai > 0 && <Tag color="volcano">⛔ {s.n_loai} tiêu chí loại</Tag>}
    </div>
  );
}

// Hình thức dự thầu + căn cứ (dò từ HSDT/khai báo) + cảnh báo mâu thuẫn.
function HinhThucBanner({ v }: { v: VendorEval }) {
  const p = v.vendor_profile;
  if (!p) return null;
  return (
    <div style={{ marginTop: 4 }}>
      <span style={{ fontSize: 13, color: "var(--ink-muted)" }}>
        Hình thức dự thầu:{" "}
        <b style={{ color: "var(--ink)" }}>{p.hinh_thuc || "không rõ"}</b>
        {" "}— căn cứ: {p.nguon}{p.do_tin > 0 && ` (độ tin ${p.do_tin.toFixed(2)})`}
      </span>
      {p.bang_chung && (
        <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>“{p.bang_chung}”</div>
      )}
      {p.mau_thuan && (
        <div style={{ marginTop: 6, padding: "8px 12px", borderRadius: 6,
                      background: "var(--partial-bg)", color: "var(--partial)", fontSize: 13 }}>
          ⚠️ MÂU THUẪN hình thức: {p.ghi_chu} — mọi nội dung liên danh VẪN được chấm đầy đủ; cần xác minh.
        </div>
      )}
    </div>
  );
}

function VendorSection({ v, onOverride }: {
  v: VendorEval;
  onOverride: (id: number, payload: Record<string, unknown>) => void;
}) {
  const biLoai = v.criteria.some((c) => c.loai);
  const files = filesOf(v);
  const phatHien = v.phat_hien_bo_sung ?? [];
  return (
    <div style={{ background: "var(--paper)", border: "1px solid var(--line)", borderRadius: 8,
                  overflow: "hidden", marginBottom: 20 }}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 16, padding: "16px 20px",
                    borderBottom: "1px solid var(--line)", background: "var(--surface)" }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: "0.06em",
                        textTransform: "uppercase", color: "var(--ink-muted)", marginBottom: 2 }}>
            Nhà thầu
          </div>
          <div style={{ fontSize: 16, fontWeight: 700, color: "var(--ink)" }}>
            {v.ten} {biLoai && <Tag color="volcano" style={{ marginLeft: 8 }}>Bị loại (tiên quyết)</Tag>}
          </div>
          <HinhThucBanner v={v} />
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
              children: (
                <>
                  {c.yeu_cau_goc && (
                    <div style={{ marginBottom: 8, fontSize: 13, color: "var(--ink-muted)" }}>
                      <b>Yêu cầu gốc (HSMT):</b> {c.yeu_cau_goc}
                    </div>
                  )}
                  <VerdictTable verdicts={c.verdicts} files={files} onOverride={onOverride} />
                </>
              ),
            }))}
          />
        )}

        {phatHien.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: "var(--ink)", marginBottom: 8 }}>
              🔎 Phát hiện của hệ thống (ngoài checklist HSMT)
            </div>
            <VerdictTable verdicts={phatHien} files={files} onOverride={onOverride} />
          </div>
        )}
      </div>
    </div>
  );
}

export default function Evaluation() {
  const { id } = useParams();
  const nav = useNavigate();
  const [sp, setSp] = useSearchParams();
  const [data, setData] = useState<EvalResultsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const load = () => {
    setLoading(true); setErr(null);
    api.get(`/packages/${id}/results`)
      .then((r) => setData(unwrap<EvalResultsPayload>(r)))
      .catch((e) => setErr(e.message)).finally(() => setLoading(false));
  };

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

  if (!data) return (
    <div>
      <Button type="text" size="small" icon={<ArrowLeftOutlined />}
        onClick={() => nav(`/packages/${id}`)} style={{ marginBottom: 8, paddingLeft: 0 }}>
        Quay lại gói thầu
      </Button>
      <Loader loading={loading} error={err} onRetry={load}><div /></Loader>
    </div>
  );

  const isErr = (s: Verdict) => s.ket_qua === "lỗi" && !s.overridden;
  const hasError = data.vendors.some((v) =>
    v.criteria.some((c) => c.verdicts.some(isErr)) || (v.phat_hien_bo_sung ?? []).some(isErr));

  const vendors = data.vendors;
  const active = vendors.some((v) => String(v.vendor_id) === sp.get("vendor"))
    ? sp.get("vendor")!
    : vendors.length > 0 ? String(vendors[0].vendor_id) : "";

  return (
    <div>
      <Button type="text" size="small" icon={<ArrowLeftOutlined />}
        onClick={() => nav(`/packages/${id}`)} style={{ marginBottom: 8, paddingLeft: 0 }}>
        Quay lại gói thầu
      </Button>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 16 }}>
        <div>
          <span className="page-eyebrow">Kết quả đánh giá</span>
          <h1 className="page-title" style={{ marginBottom: 0 }}>Phán quyết có dẫn chứng</h1>
        </div>
        <Tooltip title={hasError ? "Còn verdict AI lỗi — hãy xử lý trước khi xuất" : ""}>
          <span style={{ display: "inline-flex", gap: 8 }}>
            <Button icon={<DownloadOutlined />} disabled={hasError} onClick={() => genReport("word")}>Xuất Word (cả gói)</Button>
            <Button icon={<DownloadOutlined />} disabled={hasError} onClick={() => genReport("excel")}>Xuất Excel (cả gói)</Button>
          </span>
        </Tooltip>
      </div>

      {vendors.length === 0 ? (
        <div style={{ textAlign: "center", padding: "60px 0", background: "var(--paper)",
                      border: "1px solid var(--line)", borderRadius: 8, color: "var(--ink-muted)", fontSize: 14 }}>
          Chưa có kết quả. Hãy chạy đánh giá trước.
        </div>
      ) : (
        <Tabs activeKey={active} onChange={(k) => setSp({ vendor: k }, { replace: true })}
          items={vendors.map((v: VendorEval) => ({
            key: String(v.vendor_id),
            label: (
              <span>
                {v.criteria.some((c) => c.loai) && <Badge color="red" style={{ marginRight: 6 }} />}
                {v.ten}
              </span>
            ),
            children: <VendorSection v={v} onOverride={onOverride} />,
          }))} />
      )}
    </div>
  );
}
