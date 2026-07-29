import { useState, useEffect } from "react";
import { Badge, Button, Collapse, Input, Select, Table, Tabs, Tag, Tooltip, message } from "antd";
import { ArrowLeftOutlined, DownloadOutlined } from "@ant-design/icons";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import type { CriterionEval, EvalResultsPayload, Verdict, VendorEval } from "../api/types";
import { useArtifactLabel } from "../api/artifacts";
import Loader from "../components/Loader";
import TieuDeTieuChi, { biCat } from "../components/TieuDeTieuChi";

const KQ_OPTS = [
  { value: "đạt", label: "Đạt" },
  { value: "không đạt", label: "Không đạt" },
  { value: "cần làm rõ", label: "Cần làm rõ" },
  { value: "không áp dụng", label: "Không áp dụng" },
];

function pillClass(kq: string): string {
  if (kq === "đạt") return "dat";
  if (kq === "không đạt") return "khong-dat";
  if (kq === "lỗi") return "loi";
  if (kq === "không áp dụng") return "khong-ap-dung";   // trung tính (xám), khác cam "cần làm rõ"
  return "can-lam-ro";   // cần làm rõ | thiếu hồ sơ
}

function ResultPill({ kq }: { kq: string }) {
  // Không viết hoa: "CẦN LÀM RÕ" là thứ được quét mắt nhiều nhất trang này, mà viết hoa tiếng Việt
  // làm dấu bó sát và chậm đọc. Hoa đầu câu là đủ để tách khỏi tên tiêu chí.
  const label = kq === "lỗi" ? "Lỗi AI" : kq.charAt(0).toUpperCase() + kq.slice(1);
  return <span className={`verdict-result-pill ${pillClass(kq)}`}>{label}</span>;
}

// Bản đồ loại hồ sơ -> file, để hiện bằng chứng dạng "don_du_thau (don.pdf) tr.3" (truy vết được).
function filesOf(v: VendorEval): Record<string, string[]> {
  const m: Record<string, string[]> = {};
  (v.ho_so_nhan_duoc ?? []).forEach((h) => { m[h.loai_ho_so] = h.files; });
  return m;
}

function nguonHsdt(vd: Verdict, files: Record<string, string[]>, nhan: (c: string) => string): string {
  const loais = vd.nguon_doc && vd.nguon_doc.length > 0 ? vd.nguon_doc : [vd.hsdt_kiem_tra];
  const parts = loais.filter(Boolean).map((t) => {
    const fs = files[t];
    return fs && fs.length ? `${nhan(t)} — ${fs.join(", ")}` : nhan(t);
  });
  const tr = vd.trang?.length ? `tr.${vd.trang.join(",")}` : "không nêu trang";
  return `${parts.join("; ")} · ${tr}`;
}

function VerdictTable({ verdicts, files, onOverride }: {
  verdicts: Verdict[];
  files: Record<string, string[]>;
  onOverride: (id: number, payload: Record<string, unknown>) => void;
}) {
  const nhan = useArtifactLabel();
  return (
    <Table<Verdict>
      rowKey="id"
      dataSource={verdicts}
      pagination={false}
      size="small"
      scroll={{ x: 1020 }}
      columns={[
        {
          title: "Nội dung kiểm tra", width: 160,
          render: (_, v) => (
            <div>
              <div style={{ fontWeight: 600 }}>{v.noi_dung_kiem_tra}</div>
              <div style={{ fontSize: "var(--fs-label)", color: "var(--ink-muted)" }}>
                Hồ sơ: {nhan(v.hsdt_kiem_tra)}
              </div>
            </div>
          ),
        },
        {
          title: "Yêu cầu", width: 160,
          render: (_, v) => (
            <div>
              <div>{v.yeu_cau || <span style={{ color: "var(--ink-muted)" }}>—</span>}</div>
            </div>
          ),
        },
        {
          title: "Chuẩn theo HSMT", width: 250,
          render: (_, v) => (
            <div>
              <div>{v.thong_tin_bo_sung || <span style={{ color: "var(--ink-muted)" }}>—</span>}</div>
              {v.nguon_hsmt && (
                <div className="mono" style={{ fontSize: "var(--fs-label)", color: "var(--ink-muted)" }}>
                  {v.nguon_hsmt}
                </div>
              )}
            </div>
          ),
        },
        {
          title: "Kết quả", width: 125,
          render: (_, v) => (
            <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)", flexWrap: "wrap" }}>
              <Select
                size="small" style={{ width: 150 }} value={v.ket_qua} options={KQ_OPTS}
                onChange={(kq) => onOverride(v.id, { ket_qua: kq })}
              />
              {v.overridden && <Tag color="blue">đã sửa</Tag>}
            </div>
          ),
        },
        {
          // Độ tin gộp vào đây thay vì đứng cột riêng: nó là thuộc tính CỦA bằng chứng, tách ra
          // vừa tốn 66px vừa bắt mắt nhảy ngang để ghép lại hai thứ vốn đi cùng nhau.
          title: "Bằng chứng trong HSDT", width: 280,
          render: (_, v) => (
            <div>
              <div>{v.bang_chung || <span style={{ color: "var(--ink-muted)" }}>—</span>}</div>
              <div className="mono" style={{ fontSize: "var(--fs-label)", color: "var(--ink-muted)" }}>
                {nguonHsdt(v, files, nhan)}
                {v.do_tin > 0 && <> · độ tin {v.do_tin.toFixed(2)}</>}
              </div>
            </div>
          ),
        },
        {
          title: "Ghi chú", width: 200,
          render: (_, v) => (
            <Input.TextArea
              size="small" autoSize={{ minRows: 1, maxRows: 10 }} defaultValue={v.ghi_chu}
              placeholder="Nhận định của bạn…"
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
    <div style={{ display: "flex", gap: "var(--sp-2)", alignItems: "center", flexWrap: "wrap" }}>
      {/* Số 0 tô màu cảnh báo là nhiễu thị giác: mắt bị kéo về chỗ không có vấn đề gì. Chỉ tô khi
          thực sự có số đếm. */}
      <Tag>{s.n_tieu_chi} tiêu chí</Tag>
      <Tag color={s.n_dat > 0 ? "green" : undefined}>{s.n_dat} đạt</Tag>
      <Tag color={s.n_khong_dat > 0 ? "red" : undefined}>{s.n_khong_dat} không đạt</Tag>
      <Tag color={s.n_can_lam_ro > 0 ? "orange" : undefined}>{s.n_can_lam_ro} cần làm rõ</Tag>
      {(s.n_khong_ap_dung ?? 0) > 0 && <Tag>{s.n_khong_ap_dung} không áp dụng</Tag>}
    </div>
  );
}

// Hình thức dự thầu + căn cứ (dò từ HSDT/khai báo) + cảnh báo mâu thuẫn.
function HinhThucBanner({ v }: { v: VendorEval }) {
  const p = v.vendor_profile;
  if (!p) return null;
  return (
    <div style={{ marginTop: "var(--sp-2)" }}>
      <span style={{ fontSize: "var(--fs-body)", color: "var(--ink-muted)" }}>
        Hình thức dự thầu:{" "}
        <b style={{ color: "var(--ink)" }}>{p.hinh_thuc || "không rõ"}</b>
      </span>
      {p.bang_chung && (
        <div style={{ fontSize: "var(--fs-label)", color: "var(--ink-muted)" }}>“{p.bang_chung}”</div>
      )}
      {p.mau_thuan && (
        <div style={{ marginTop: "var(--sp-2)", padding: "var(--sp-2) var(--sp-3)", borderRadius: 6,
                      background: "var(--partial-bg)", color: "var(--partial)", fontSize: "var(--fs-body)" }}>
          <b>Mâu thuẫn hình thức dự thầu.</b> {p.ghi_chu}. Các nội dung dành cho liên danh vẫn được
          chấm đầy đủ — hãy xác minh trước khi kết luận.
        </div>
      )}
    </div>
  );
}

function VendorSection({ v, onOverride }: {
  v: VendorEval;
  onOverride: (id: number, payload: Record<string, unknown>) => void;
}) {
  const files = filesOf(v);
  return (
    <div style={{ background: "var(--paper)", border: "1px solid var(--line)", borderRadius: 8,
                  overflow: "hidden", marginBottom: "var(--sp-5)" }}>
      {/* Một cột dọc: tên → tổng hợp → căn cứ. Trước đây chip tổng hợp neo bên phải một khối cao
          4 dòng nên nó trôi lơ lửng, mắt phải nhảy ngang rồi quay lại mới ghép được tên với kết quả. */}
      <div style={{ padding: "var(--sp-4) var(--sp-5)", borderBottom: "1px solid var(--line)",
                    background: "var(--surface)" }}>
        <div style={{ fontSize: "var(--fs-lead)", fontWeight: 700, color: "var(--ink)",
                      display: "flex", alignItems: "center", gap: "var(--sp-2)", flexWrap: "wrap" }}>
          {v.ten}
        </div>
        <div style={{ marginTop: "var(--sp-2)" }}><SummaryChips v={v} /></div>
        <HinhThucBanner v={v} />
      </div>

      <div style={{ padding: "var(--sp-3) var(--sp-4) var(--sp-4)" }}>
        {v.criteria.length === 0 ? (
          <div style={{ textAlign: "center", padding: "var(--sp-5) 0", color: "var(--ink-muted)", fontSize: "var(--fs-body)" }}>
            Chưa có kết quả đánh giá
          </div>
        ) : (
          <Collapse
            items={v.criteria.map((c: CriterionEval) => ({
              key: String(c.eval_id),
              label: (
                // Neo vào nguyên văn điều khoản HSMT, không dùng `ten` do LLM chế (mất dấu, sai
                // chính tả, đổi mỗi lần chạy). Pill trạng thái đứng đầu vì đây là màn QUÉT: mắt
                // tìm cái trượt trước, rồi mới đọc điều khoản.
                <div style={{ display: "flex", alignItems: "flex-start", gap: "var(--sp-3)" }}>
                  <span style={{ flex: "0 0 auto", marginTop: 2 }}><ResultPill kq={c.ket_qua} /></span>
                  <TieuDeTieuChi yeuCauGoc={c.yeu_cau_goc} ten={c.ten} max={130} />
                  {c.nhom === "phat_hien_bo_sung" && (
                    <Tag color="blue" style={{ flex: "0 0 auto" }}>Hệ thống tự kiểm</Tag>
                  )}
                </div>
              ),
              children: (
                <>
                  {/* Nhãn Collapse đã là điều khoản (rút gọn) — chỉ hiện bản đầy đủ khi bị cắt. */}
                  {c.yeu_cau_goc && biCat(c.yeu_cau_goc, 130) && (
                    <div style={{ marginBottom: "var(--sp-2)", fontSize: "var(--fs-body)", color: "var(--ink-muted)" }}>
                      <b>Yêu cầu gốc (HSMT):</b> {c.yeu_cau_goc}
                    </div>
                  )}
                  <VerdictTable verdicts={c.verdicts} files={files} onOverride={onOverride} />
                </>
              ),
            }))}
          />
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
      message.success("Đã lưu chỉnh sửa của chuyên gia");
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
        onClick={() => nav(`/packages/${id}`)} style={{ marginBottom: "var(--sp-2)", paddingLeft: 0 }}>
        Quay lại gói thầu
      </Button>
      <Loader loading={loading} error={err} onRetry={load}><div /></Loader>
    </div>
  );

  const isErr = (s: Verdict) => s.ket_qua === "lỗi" && !s.overridden;
  const hasError = data.vendors.some((v) =>
    v.criteria.some((c) => c.verdicts.some(isErr)));

  const vendors = data.vendors;
  const active = vendors.some((v) => String(v.vendor_id) === sp.get("vendor"))
    ? sp.get("vendor")!
    : "tong_hop";   // mặc định mở bảng tổng hợp so sánh nhà thầu

  return (
    <div>
      {/* Nút quay lại nằm CÙNG hàng tiêu đề: trước đây trang có 4 dải xếp chồng (nút → eyebrow →
          tiêu đề → tabs) trước khi tới nội dung, đẩy phần việc thật xuống quá sâu. */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
                    gap: "var(--sp-4)", marginBottom: "var(--sp-4)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)" }}>
          <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => nav(`/packages/${id}`)}
            style={{ paddingLeft: 0 }} aria-label="Quay lại gói thầu" />
          <h1 className="page-title" style={{ marginBottom: 0 }}>Kết quả đánh giá</h1>
        </div>
        <Tooltip title={hasError ? "Còn kết quả AI báo lỗi chưa xử lý — hãy chỉnh lại trước khi xuất báo cáo" : ""}>
          <span style={{ display: "inline-flex", gap: "var(--sp-2)" }}>
            <Button icon={<DownloadOutlined />} disabled={hasError} onClick={() => genReport("word")}>Báo cáo Word</Button>
            <Button icon={<DownloadOutlined />} disabled={hasError} onClick={() => genReport("excel")}>Báo cáo Excel</Button>
          </span>
        </Tooltip>
      </div>

      {vendors.length === 0 ? (
        <div style={{ textAlign: "center", padding: "var(--sp-6) 0", background: "var(--paper)",
                      border: "1px solid var(--line)", borderRadius: 8, color: "var(--ink-muted)", fontSize: "var(--fs-body)" }}>
          Chưa có kết quả đánh giá. Quay lại gói thầu, chọn một nhà thầu rồi bấm “Chạy đánh giá”.
        </div>
      ) : (
        <Tabs activeKey={active} onChange={(k) => setSp({ vendor: k }, { replace: true })}
          items={[
            { key: "tong_hop", label: "Tổng hợp",
              children: <SummaryTable vendors={vendors} onOpen={(vid) => setSp({ vendor: String(vid) }, { replace: true })} /> },
            ...vendors.map((v: VendorEval) => ({
              key: String(v.vendor_id),
              label: (
                <span>
                  {v.summary.n_khong_dat > 0 && <Badge color="red" style={{ marginRight: "var(--sp-2)" }} />}
                  {v.ten}
                </span>
              ),
              children: <VendorSection v={v} onOverride={onOverride} />,
            })),
          ]} />
      )}
    </div>
  );
}

// ── Bảng tổng hợp so sánh nhà thầu (ra quyết định nhanh) ───────────────────────────────
function SummaryTable({ vendors, onOpen }: { vendors: VendorEval[]; onOpen: (vid: number) => void }) {
  return (
    <div style={{ border: "1px solid var(--line)", borderRadius: 8, overflow: "hidden" }}>
    <Table<VendorEval> rowKey="vendor_id" dataSource={vendors} pagination={false} size="small"
      onRow={(v) => ({ onClick: () => onOpen(v.vendor_id), style: { cursor: "pointer" } })}
      columns={[
        { title: "Nhà thầu", render: (_, v) => <span style={{ fontWeight: 600 }}>{v.ten}</span> },
        { title: "Hình thức", width: 120,
          render: (_, v) => <span style={{ color: "var(--ink-muted)" }}>{v.hinh_thuc || v.vendor_profile?.hinh_thuc || "—"}</span> },
        /* Máy KHÔNG kết luận loại/không loại — chỉ nêu trạng thái để chuyên gia tự quyết. */
        { title: "Trạng thái", width: 150, render: (_, v) =>
          v.criteria.length === 0
            ? <Tag>Chưa chấm</Tag>
            : v.summary.n_khong_dat > 0
              ? <Tag color="volcano">Có tiêu chí không đạt</Tag>
              : v.summary.n_can_lam_ro > 0
                ? <Tag color="orange">Cần làm rõ</Tag>
                : <Tag color="green">Đạt toàn bộ</Tag> },
        { title: "Đạt", width: 70, align: "center", render: (_, v) => v.summary.n_dat },
        { title: "Không đạt", width: 100, align: "center",
          render: (_, v) => v.summary.n_khong_dat > 0
            ? <span style={{ color: "var(--fail)", fontWeight: 600 }}>{v.summary.n_khong_dat}</span> : 0 },
        { title: "Cần làm rõ", width: 105, align: "center",
          render: (_, v) => v.summary.n_can_lam_ro > 0
            ? <span style={{ color: "var(--partial)", fontWeight: 600 }}>{v.summary.n_can_lam_ro}</span> : 0 },
        { title: "Không áp dụng", width: 120, align: "center",
          render: (_, v) => v.summary.n_khong_ap_dung ?? 0 },
        { title: "", width: 100, render: (_, v) => <a onClick={() => onOpen(v.vendor_id)}>Chi tiết →</a> },
      ]} />
    </div>
  );
}
