import { useEffect, useState } from "react";
import {
  Badge, Button, Card, Empty, Input, Modal, Popconfirm, Select, Steps, Table, Tabs, Tag, Tooltip, Upload, message,
} from "antd";
import { CheckCircleOutlined, DeleteOutlined, EditOutlined, PlusOutlined, UploadOutlined } from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import type { ChayTuDongOut, EvalResultsPayload, Package, TenderDoc, Vendor } from "../api/types";
import { useArtifactTypes } from "../api/artifacts";
import StatusTag from "../components/StatusTag";
import Loader from "../components/Loader";

const HINH_THUC_OPTS = [
  { value: "doc_lap", label: "Độc lập" },
  { value: "lien_danh", label: "Liên danh" },
];

type ArtOpt = { value: string; label: string };

// Pipeline đánh giá hiện thuần PDF (vision) — chặn từ bước chọn file để không tải lên rồi mới báo lỗi.
const PDF_ONLY = "Chỉ hỗ trợ file PDF — Excel sẽ được bổ sung sau";
const isPdf = (f: File) => f.name.toLowerCase().endsWith(".pdf");

function OcrBadge({ st }: { st: string }) {
  const err = st.startsWith("loi");
  const ok = st === "hoan_thanh";
  // "OCR" là thuật ngữ kỹ thuật, lại sai với PDF text (không hề OCR). Nói theo việc người dùng
  // quan tâm: hệ thống đã đọc được file hay chưa.
  return <Tooltip title={err ? st : ""}>
    <Tag color={ok ? "green" : err ? "red" : "orange"}>
      {ok ? "Đã đọc" : err ? "Đọc lỗi" : "Đang đọc"}
    </Tag>
  </Tooltip>;
}

// ── Bảng hồ sơ (của 1 nhà thầu hoặc dùng chung) — đổi loại tại chỗ + xóa ───────────────
function DocTable({ docs, artifactTypes, onChangeType, onDelete }: {
  docs: TenderDoc[]; artifactTypes: ArtOpt[];
  onChangeType: (id: number, at: string) => void; onDelete: (id: number) => void;
}) {
  if (docs.length === 0)
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Chưa có hồ sơ" />;
  return (
    <Table<TenderDoc> rowKey="id" dataSource={docs} pagination={false} size="small"
      columns={[
        {
          title: "Loại hồ sơ", width: 260,
          render: (_, d) => (
            <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)" }}>
              <Select size="small" style={{ minWidth: 190 }} value={d.artifact_type || undefined}
                placeholder="chọn loại" options={artifactTypes}
                onChange={(v) => onChangeType(d.id, v)} />
              {/* {d.artifact_validation?.match === false && (
                <Tooltip title={d.artifact_validation?.note || "Nghi tải nhầm loại"}>
                  <Tag color="warning">nghi nhầm loại</Tag>
                </Tooltip>
              )} */}
            </div>
          ),
        },
        { title: "Tên file", dataIndex: "file_name", render: (t, d) => t || d.file_path },
        { title: "Trạng thái", width: 120, render: (_, d) => <OcrBadge st={d.trang_thai_ocr} /> },
        {
          title: "", width: 60,
          render: (_, d) => (
            <Popconfirm title="Xóa hồ sơ này?" onConfirm={() => onDelete(d.id)}
              okText="Xóa" cancelText="Hủy">
              <Button size="small" danger type="text" icon={<DeleteOutlined />} />
            </Popconfirm>
          ),
        },
      ]} />
  );
}

// ── Nút tải hồ sơ (tự giữ loại đang chọn) ─────────────────────────────────────────────
function UploadDoc({ artifactTypes, onUpload, label = "Tải hồ sơ", disabled = false }: {
  artifactTypes: ArtOpt[]; onUpload: (file: File, at: string) => Promise<void>;
  label?: string; disabled?: boolean;
}) {
  const [at, setAt] = useState<string>();
  return (
    <div style={{ display: "flex", gap: "var(--sp-2)", marginTop: "var(--sp-3)", flexWrap: "wrap", alignItems: "center" }}>
      <Select placeholder="Chọn loại hồ sơ" style={{ minWidth: 200 }} value={at} onChange={setAt}
        options={artifactTypes} />
      <Upload showUploadList={false} accept=".pdf" disabled={disabled} beforeUpload={(f) => {
        if (!at) { message.warning("Chọn loại hồ sơ trước"); return false; }
        if (!isPdf(f)) { message.error(PDF_ONLY); return false; }
        onUpload(f, at); return false;
      }}>
        <Button icon={<UploadOutlined />} loading={disabled}>{label}</Button>
      </Upload>
    </div>
  );
}

// ── Tải tài liệu không cần loại (HSMT / TBMT) ─────────────────────────────────────────
function UploadPlain({ onUpload, label, disabled = false }: {
  onUpload: (file: File) => Promise<void>; label: string; disabled?: boolean;
}) {
  return (
    <Upload showUploadList={false} accept=".pdf" disabled={disabled} beforeUpload={(f) => {
      if (!isPdf(f)) { message.error(PDF_ONLY); return false; }
      onUpload(f); return false;
    }}>
      <Button icon={<UploadOutlined />} loading={disabled}>{label}</Button>
    </Upload>
  );
}

function DocRow({ d, onDelete }: { d: TenderDoc; onDelete: (id: number) => void }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-3)", padding: "var(--sp-2) 0" }}>
      <span style={{ fontWeight: 500 }}>{d.file_name || d.file_path}</span>
      <OcrBadge st={d.trang_thai_ocr} />
      <Popconfirm title="Xóa tài liệu này?" onConfirm={() => onDelete(d.id)} okText="Xóa" cancelText="Hủy">
        <Button size="small" danger type="text" icon={<DeleteOutlined />} />
      </Popconfirm>
    </div>
  );
}

export default function PackageDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [pkg, setPkg] = useState<Package | null>(null);
  const [docs, setDocs] = useState<TenderDoc[]>([]);
  const [active, setActive] = useState("chung");
  const [evaluating, setEvaluating] = useState<number | null>(null);
  const [modal, setModal] = useState<Vendor | "new" | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [evaluatedVids, setEvaluatedVids] = useState<Set<number>>(new Set());
  const [uploading, setUploading] = useState(false);
  const [autoRunning, setAutoRunning] = useState(false);
  const artifactTypes = useArtifactTypes() as ArtOpt[];

  const load = () => {
    setLoading(true); setErr(null);
    api.get(`/packages/${id}`).then((r) => setPkg(unwrap<Package>(r)))
      .catch((e) => setErr(e.message)).finally(() => setLoading(false));
    api.get(`/packages/${id}/documents`).then((r) => setDocs(unwrap<TenderDoc[]>(r))).catch(() => {});
    api.get(`/packages/${id}/results`).then((r) => setEvaluatedVids(new Set(
      unwrap<EvalResultsPayload>(r).vendors.filter((v) => v.criteria.length > 0).map((v) => v.vendor_id))))
      .catch(() => {});
  };
  useEffect(load, [id]);

  const uploadDoc = async (file: File, loai: string, vendorId?: number, artifactType?: string) => {
    const fd = new FormData();
    fd.append("file", file); fd.append("loai", loai);
    if (vendorId) fd.append("vendor_id", String(vendorId));
    if (artifactType) fd.append("artifact_type", artifactType);
    // Cùng khuôn với nút "Chạy đánh giá": message có key cố định + duration 0 -> thông báo đứng
    // yên cho tới khi bị chính nó thay thế, không xếp chồng.
    message.loading({ content: `Đang tải "${file.name}" và xử lý…`, key: "upload", duration: 0 });
    setUploading(true);
    try {
      const res = await api.post(`/packages/${id}/documents`, fd);
      const doc = res.data.data;
      if (doc?.artifact_validation?.match === false)
        message.warning({ content: `Nghi tải nhầm loại: ${doc.artifact_validation.note}`, key: "upload" });
      else message.success({ content: "Đã tải lên & xử lý", key: "upload" });
      load();
    } catch (e: any) { message.error({ content: e.message, key: "upload" }); }
    finally { setUploading(false); }
  };
  const changeDocType = async (docId: number, at: string) => {
    try { await api.patch(`/packages/${id}/documents/${docId}`, { artifact_type: at }); load(); }
    catch (e: any) { message.error(e.message); }
  };
  const deleteDoc = async (docId: number) => {
    try { await api.delete(`/packages/${id}/documents/${docId}`); load(); }
    catch (e: any) { message.error(e.message); }
  };

  const setHinhThuc = async (vid: number, hinh_thuc: string) => {
    try { setPkg(unwrap<Package>(await api.patch(`/packages/${id}/vendors/${vid}`, { hinh_thuc }))); }
    catch (e: any) { message.error(e.message); }
  };
  const deleteVendor = async (vid: number) => {
    try {
      setPkg(unwrap<Package>(await api.delete(`/packages/${id}/vendors/${vid}`)));
      if (active === String(vid)) setActive("chung");
      load();
      message.success("Đã xóa nhà thầu");
    } catch (e: any) { message.error(e.message); }
  };
  // Chạy trọn luồng bằng một nút. Backend BỎ QUA bước đã xong (gói đã có tiêu chí thì không bóc
  // lại, nhà thầu đã chấm thì không chấm lại), nên bấm lại sau khi thêm nhà thầu chỉ tốn tiền AI
  // cho đúng người mới.
  const runAuto = async () => {
    setAutoRunning(true);
    message.loading({ content: "Đang chạy tự động — bóc tiêu chí rồi chấm từng nhà thầu, có thể mất vài phút…",
                      key: "auto", duration: 0 });
    try {
      const d = unwrap<ChayTuDongOut>(await api.post(`/packages/${id}/chay-tu-dong`));
      const hong = d.buoc.find((b) => b.trang_thai === "loi");
      if (hong) {
        message.error({ content: `${hong.ten}: ${hong.chi_tiet}`, key: "auto" });
      } else {
        const tom_tat = d.buoc.map((b) => `${b.ten}: ${b.trang_thai === "bo_qua" ? "bỏ qua" : b.chi_tiet}`).join(" · ");
        message.success({ content: `Chạy tự động xong — ${tom_tat}`, key: "auto", duration: 6 });
      }
      // Nhà thầu lỗi KHÔNG hủy cả lô — liệt kê riêng để chuyên gia chạy lại từng người.
      if (d.loi.length) {
        Modal.info({
          title: `${d.loi.length} nhà thầu chưa chấm được`,
          content: (
            <ul style={{ paddingLeft: "var(--sp-4)", marginTop: "var(--sp-2)" }}>
              {d.loi.map((l) => <li key={l.vendor_id}><b>{l.ten}</b>: {l.error}</li>)}
            </ul>
          ),
        });
      }
      load();
    } catch (e: any) { message.error({ content: e.message, key: "auto" }); }
    finally { setAutoRunning(false); }
  };
  const evalVendor = async (vid: number) => {
    setEvaluating(vid);
    message.loading({ content: "Đang chấm HSDT — có thể mất vài phút…", key: "eval", duration: 0 });
    try {
      await api.post(`/packages/${id}/vendors/${vid}/evaluate`);
      message.success({ content: "Đánh giá hoàn tất", key: "eval" });
      load();   // cập nhật trạng thái gói (Steps -> Xem kết quả)
    } catch (e: any) { message.error({ content: e.message, key: "eval" }); }
    finally { setEvaluating(null); }
  };

  if (!pkg) return <Loader loading={loading} error={err} onRetry={load}><div /></Loader>;
  const hsmt = docs.find((d) => d.loai === "HSMT");
  const tbmt = docs.filter((d) => d.loai === "TBMT");
  const shared = docs.filter((d) => d.loai === "HSDT" && d.vendor_id == null);
  const vendorDocs = (vid: number) => docs.filter((d) => d.loai === "HSDT" && d.vendor_id === vid);

  // Mỗi loại hồ sơ chỉ nộp MỘT file. Bỏ hẳn loại đã có khỏi ô chọn thay vì để người dùng tải xong
  // mới nhận lỗi 409. Phạm vi trùng bám đúng phạm vi pipeline đọc khi chấm một nhà thầu: hồ sơ
  // RIÊNG của họ CỘNG tài liệu DÙNG CHUNG — nên tài liệu dùng chung chặn mọi nhà thầu, và ngược
  // lại loại nào đã có ở bất kỳ đâu cũng chặn ô chọn của tài liệu dùng chung.
  const loaiConLai = (vid?: number): ArtOpt[] => {
    const daCo = new Set(
      docs.filter((d) => d.loai === "HSDT" && d.artifact_type
                         && (vid === undefined || d.vendor_id == null || d.vendor_id === vid))
          .map((d) => d.artifact_type as string));
    return artifactTypes.filter((o) => !daCo.has(o.value));
  };

  // Dẫn dắt luồng: HSMT -> tiêu chí -> HSDT -> chạy đánh giá -> kết quả.
  const hasCriteria = (pkg.so_tieu_chi ?? 0) > 0;
  const hasAnyHsdt = docs.some((d) => d.loai === "HSDT" && d.vendor_id != null);
  const evaluated = pkg.trang_thai === "cho_review" || pkg.trang_thai === "hoan_thanh";
  const step = !hsmt ? 0 : !hasCriteria ? 1 : !hasAnyHsdt ? 2 : !evaluated ? 3 : 4;

  const chungTab = (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-5)" }}>
      <div>
        <div className="page-eyebrow">Hồ sơ mời thầu (HSMT) — nguồn để trích tiêu chí</div>
        {hsmt
          ? <DocRow d={hsmt} onDelete={deleteDoc} />
          : <div style={{ marginTop: "var(--sp-2)" }}><UploadPlain label="Tải HSMT" onUpload={(f) => uploadDoc(f, "HSMT")} disabled={uploading} /></div>}
      </div>
      <div>
        <div className="page-eyebrow">Thông báo mời thầu (TBMT) — mốc đóng/mở thầu</div>
        {tbmt.map((d) => <DocRow key={d.id} d={d} onDelete={deleteDoc} />)}
        <div style={{ marginTop: "var(--sp-2)" }}><UploadPlain label="Tải TBMT" onUpload={(f) => uploadDoc(f, "TBMT")} disabled={uploading} /></div>
      </div>
      <div>
        <div className="page-eyebrow">Tài liệu dùng chung — áp cho mọi nhà thầu</div>
        <DocTable docs={shared} artifactTypes={artifactTypes} onChangeType={changeDocType} onDelete={deleteDoc} />
        <UploadDoc artifactTypes={loaiConLai()} label="Tải tài liệu dùng chung"
          onUpload={(f, at) => uploadDoc(f, "HSDT", undefined, at)} disabled={uploading} />
      </div>
    </div>
  );

  const vendorTab = (v: Vendor) => (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-3)", flexWrap: "wrap", marginBottom: "var(--sp-3)" }}>
        <div style={{ flex: 1, minWidth: 200 }}>
          <div style={{ fontSize: "var(--fs-lead)", fontWeight: 700 }}>
            {v.ten}{v.ten_viet_tat ? <span style={{ color: "var(--ink-muted)", fontWeight: 400 }}> ({v.ten_viet_tat})</span> : null}
          </div>
        </div>
        <Select size="small" style={{ minWidth: 170 }} allowClear placeholder="Hình thức: tự dò"
          value={v.hinh_thuc || undefined} options={HINH_THUC_OPTS}
          onChange={(val) => setHinhThuc(v.id, val ?? "")} />
        <Tooltip title={!hasCriteria ? "Chưa có tiêu chí — hãy trích và chốt tiêu chí trước"
          : vendorDocs(v.id).length === 0 ? "Nhà thầu này chưa có hồ sơ nào" : ""}>
          <span>
            <Button size="small" type="primary" loading={evaluating === v.id}
              disabled={evaluating !== null || !hasCriteria || vendorDocs(v.id).length === 0}
              onClick={() => evalVendor(v.id)}>Chạy đánh giá</Button>
          </span>
        </Tooltip>
        <Button size="small" onClick={() => nav(`/packages/${id}/evaluation?vendor=${v.id}`)}>
          Xem kết quả</Button>
        {/* Thao tác phá hủy tách khỏi nút chính bằng vạch ngăn — tránh bấm nhầm "Xóa" khi định
            bấm "Chạy đánh giá". */}
        <span style={{ width: 1, height: 20, background: "var(--line)", margin: "0 2px" }} />
        <Button size="small" icon={<EditOutlined />} onClick={() => setModal(v)}>Sửa</Button>
        <Popconfirm title="Xóa nhà thầu này?"
          description="Xóa cả hồ sơ đã tải và kết quả đánh giá của nhà thầu."
          onConfirm={() => deleteVendor(v.id)} okText="Xóa" cancelText="Hủy"
          okButtonProps={{ danger: true }}>
          <Button size="small" danger icon={<DeleteOutlined />}>Xóa</Button>
        </Popconfirm>
      </div>
      <DocTable docs={vendorDocs(v.id)} artifactTypes={artifactTypes}
        onChangeType={changeDocType} onDelete={deleteDoc} />
      <UploadDoc artifactTypes={loaiConLai(v.id)} label="Tải hồ sơ nhà thầu"
        onUpload={(f, at) => uploadDoc(f, "HSDT", v.id, at)} disabled={uploading} />
    </div>
  );

  const vendorLabel = (v: Vendor) => {
    const n = vendorDocs(v.id).length;
    return (
      <span>
        {evaluatedVids.has(v.id) && (
          <Tooltip title="Đã chấm"><CheckCircleOutlined style={{ color: "var(--pass)", marginRight: "var(--sp-2)" }} /></Tooltip>
        )}
        {v.ten}
        <Tooltip title={n === 0 ? "Chưa có hồ sơ" : `${n} hồ sơ`}>
          <Badge count={n} showZero size="small" color={n === 0 ? "#d9d9d9" : "#0F6E62"}
            style={{ marginLeft: "var(--sp-2)" }} />
        </Tooltip>
      </span>
    );
  };

  const items = [
    { key: "chung", label: "Tài liệu chung", children: chungTab },
    ...pkg.vendors.map((v) => ({ key: String(v.id), label: vendorLabel(v), children: vendorTab(v) })),
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end",
                    gap: "var(--sp-4)", marginBottom: "var(--sp-5)", flexWrap: "wrap" }}>
        <div>
          <span className="page-eyebrow">Gói thầu {pkg.ma_so} · <StatusTag status={pkg.trang_thai} /></span>
          <h1 className="page-title" style={{ marginBottom: 0 }}>{pkg.ten}</h1>
        </div>
        <div style={{ display: "flex", gap: "var(--sp-2)" }}>
          <Button onClick={() => nav(`/packages/${id}/rubric`)}>Tiêu chuẩn đánh giá</Button>
          <Button type="primary" onClick={() => nav(`/packages/${id}/evaluation`)}>Xem kết quả</Button>
        </div>
      </div>

      <Card style={{ marginBottom: "var(--sp-4)" }}>
        <Steps size="small" current={step} items={[
          { title: "Tải HSMT" }, { title: "Chốt tiêu chí" }, { title: "Tải hồ sơ nhà thầu" },
          { title: "Chạy đánh giá" }, { title: "Xem kết quả" },
        ]} />
        {/* Nút tắt cho cả luồng trên. Đặt ngay dưới Steps để thấy rõ nó thay cho việc bấm tay
            từng bước, chứ không phải một hành động khác. */}
        <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-3)",
                      marginTop: "var(--sp-4)", flexWrap: "wrap" }}>
          <Button type="primary" loading={autoRunning} disabled={!hsmt || autoRunning}
            onClick={runAuto}>Chạy tự động</Button>
          <span style={{ color: "var(--ink-muted)", fontSize: "var(--fs-label)" }}>
            {hsmt
              ? "Bóc tiêu chí từ HSMT rồi chấm mọi nhà thầu — bỏ qua bước đã xong."
              : "Tải HSMT trước đã."}
          </span>
        </div>
      </Card>

      <Card styles={{ body: { paddingTop: "var(--sp-2)" } }}>
        <Tabs activeKey={active} onChange={setActive} items={items}
          tabBarExtraContent={
            <Button type="dashed" icon={<PlusOutlined />} onClick={() => setModal("new")}>Thêm nhà thầu</Button>} />
      </Card>

      <VendorModal open={modal !== null} vendor={modal === "new" ? null : modal}
        onClose={() => setModal(null)}
        onSaved={(p) => { setPkg(p); setModal(null); }} pkgId={id!} />
    </div>
  );
}

// ── Modal thêm / sửa nhà thầu ─────────────────────────────────────────────────────────
function VendorModal({ open, vendor, pkgId, onClose, onSaved }: {
  open: boolean; vendor: Vendor | null; pkgId: string;
  onClose: () => void; onSaved: (p: Package) => void;
}) {
  const [ten, setTen] = useState("");
  const [tt, setTt] = useState("");
  const [ht, setHt] = useState<string>("");
  useEffect(() => {
    setTen(vendor?.ten ?? ""); setTt(vendor?.ten_viet_tat ?? ""); setHt(vendor?.hinh_thuc ?? "");
  }, [vendor, open]);

  const save = async () => {
    if (!ten.trim()) { message.warning("Nhập tên nhà thầu"); return; }
    const body = { ten: ten.trim(), ten_viet_tat: tt.trim(), hinh_thuc: ht };
    try {
      const r = vendor
        ? await api.patch(`/packages/${pkgId}/vendors/${vendor.id}`, body)
        : await api.post(`/packages/${pkgId}/vendors`, body);
      onSaved(unwrap<Package>(r));
      message.success(vendor ? "Đã cập nhật nhà thầu" : "Đã thêm nhà thầu");
    } catch (e: any) { message.error(e.message); }
  };

  return (
    <Modal open={open} onCancel={onClose} onOk={save} okText="Lưu" cancelText="Hủy"
      title={vendor ? "Sửa nhà thầu" : "Thêm nhà thầu"} destroyOnHidden>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-3)", marginTop: "var(--sp-2)" }}>
        <Input placeholder="Tên đầy đủ" value={ten} onChange={(e) => setTen(e.target.value)} />
        <Input placeholder="Tên viết tắt (khớp webform)" value={tt} onChange={(e) => setTt(e.target.value)} />
        <Select placeholder="Hình thức dự thầu (để trống = tự dò)" value={ht || undefined} allowClear
          onChange={(v) => setHt(v ?? "")} options={HINH_THUC_OPTS} />
      </div>
    </Modal>
  );
}
