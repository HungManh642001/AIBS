import { useEffect, useState } from "react";
import {
  Button, Card, Empty, Input, Modal, Popconfirm, Select, Steps, Table, Tabs, Tag, Tooltip, Upload, message,
} from "antd";
import { DeleteOutlined, EditOutlined, PlusOutlined, UploadOutlined } from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import type { Package, TenderDoc, Vendor } from "../api/types";
import { useArtifactTypes } from "../api/artifacts";
import StatusTag from "../components/StatusTag";
import Loader from "../components/Loader";

const HINH_THUC_OPTS = [
  { value: "doc_lap", label: "Độc lập" },
  { value: "lien_danh", label: "Liên danh" },
];

type ArtOpt = { value: string; label: string };

function OcrBadge({ st }: { st: string }) {
  const err = st.startsWith("loi");
  const ok = st === "hoan_thanh";
  return <Tag color={ok ? "green" : err ? "red" : "orange"}>
    {ok ? "OCR xong" : err ? "OCR lỗi" : "đang xử lý"}
  </Tag>;
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
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <Select size="small" style={{ minWidth: 190 }} value={d.artifact_type || undefined}
                placeholder="chọn loại" options={artifactTypes}
                onChange={(v) => onChangeType(d.id, v)} />
              {d.artifact_validation?.match === false && (
                <Tooltip title={d.artifact_validation?.note || "Nghi tải nhầm loại"}>
                  <Tag color="warning">nghi nhầm loại</Tag>
                </Tooltip>
              )}
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
function UploadDoc({ artifactTypes, onUpload, label = "Tải hồ sơ" }: {
  artifactTypes: ArtOpt[]; onUpload: (file: File, at: string) => Promise<void>; label?: string;
}) {
  const [at, setAt] = useState<string>();
  return (
    <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap", alignItems: "center" }}>
      <Select placeholder="Chọn loại hồ sơ" style={{ minWidth: 200 }} value={at} onChange={setAt}
        options={artifactTypes} />
      <Upload showUploadList={false} beforeUpload={(f) => {
        if (!at) { message.warning("Chọn loại hồ sơ trước"); return false; }
        onUpload(f, at); return false;
      }}>
        <Button icon={<UploadOutlined />}>{label}</Button>
      </Upload>
    </div>
  );
}

// ── Tải tài liệu không cần loại (HSMT / TBMT) ─────────────────────────────────────────
function UploadPlain({ onUpload, label }: { onUpload: (file: File) => Promise<void>; label: string }) {
  return (
    <Upload showUploadList={false} beforeUpload={(f) => { onUpload(f); return false; }}>
      <Button icon={<UploadOutlined />}>{label}</Button>
    </Upload>
  );
}

function DocRow({ d, onDelete }: { d: TenderDoc; onDelete: (id: number) => void }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "6px 0" }}>
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
  const artifactTypes = useArtifactTypes() as ArtOpt[];

  const load = () => {
    setLoading(true); setErr(null);
    api.get(`/packages/${id}`).then((r) => setPkg(unwrap<Package>(r)))
      .catch((e) => setErr(e.message)).finally(() => setLoading(false));
    api.get(`/packages/${id}/documents`).then((r) => setDocs(unwrap<TenderDoc[]>(r))).catch(() => {});
  };
  useEffect(load, [id]);

  const uploadDoc = async (file: File, loai: string, vendorId?: number, artifactType?: string) => {
    const fd = new FormData();
    fd.append("file", file); fd.append("loai", loai);
    if (vendorId) fd.append("vendor_id", String(vendorId));
    if (artifactType) fd.append("artifact_type", artifactType);
    try {
      const res = await api.post(`/packages/${id}/documents`, fd);
      const doc = res.data.data;
      if (doc?.artifact_validation?.match === false)
        message.warning(`Nghi tải nhầm loại: ${doc.artifact_validation.note}`);
      else message.success("Đã tải lên & xử lý");
      load();
    } catch (e: any) { message.error(e.message); }
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

  // Dẫn dắt luồng: HSMT -> tiêu chí -> HSDT -> chạy đánh giá -> kết quả.
  const hasCriteria = (pkg.so_tieu_chi ?? 0) > 0;
  const hasAnyHsdt = docs.some((d) => d.loai === "HSDT" && d.vendor_id != null);
  const evaluated = pkg.trang_thai === "cho_review" || pkg.trang_thai === "hoan_thanh";
  const step = !hsmt ? 0 : !hasCriteria ? 1 : !hasAnyHsdt ? 2 : !evaluated ? 3 : 4;

  const chungTab = (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div>
        <div className="page-eyebrow">HSMT — hồ sơ mời thầu (bóc tiêu chí)</div>
        {hsmt
          ? <DocRow d={hsmt} onDelete={deleteDoc} />
          : <div style={{ marginTop: 8 }}><UploadPlain label="Tải HSMT" onUpload={(f) => uploadDoc(f, "HSMT")} /></div>}
      </div>
      <div>
        <div className="page-eyebrow">TBMT — thông báo mời thầu (mốc đóng/mở thầu)</div>
        {tbmt.map((d) => <DocRow key={d.id} d={d} onDelete={deleteDoc} />)}
        <div style={{ marginTop: 8 }}><UploadPlain label="Tải TBMT" onUpload={(f) => uploadDoc(f, "TBMT")} /></div>
      </div>
      <div>
        <div className="page-eyebrow">Dùng chung cả gói (webform / kết quả mở thầu…)</div>
        <DocTable docs={shared} artifactTypes={artifactTypes} onChangeType={changeDocType} onDelete={deleteDoc} />
        <UploadDoc artifactTypes={artifactTypes} label="Tải tài liệu dùng chung"
          onUpload={(f, at) => uploadDoc(f, "HSDT", undefined, at)} />
      </div>
    </div>
  );

  const vendorTab = (v: Vendor) => (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", marginBottom: 12 }}>
        <div style={{ flex: 1, minWidth: 200 }}>
          <div style={{ fontSize: 16, fontWeight: 700 }}>
            {v.ten}{v.ten_viet_tat ? <span style={{ color: "var(--ink-muted)", fontWeight: 400 }}> ({v.ten_viet_tat})</span> : null}
          </div>
        </div>
        <Select size="small" style={{ minWidth: 170 }} allowClear placeholder="Hình thức: tự dò"
          value={v.hinh_thuc || undefined} options={HINH_THUC_OPTS}
          onChange={(val) => setHinhThuc(v.id, val ?? "")} />
        <Button size="small" icon={<EditOutlined />} onClick={() => setModal(v)}>Sửa</Button>
        <Popconfirm title="Xóa nhà thầu này? (kèm hồ sơ & kết quả đánh giá)"
          onConfirm={() => deleteVendor(v.id)} okText="Xóa" cancelText="Hủy">
          <Button size="small" danger icon={<DeleteOutlined />}>Xóa</Button>
        </Popconfirm>
        <Tooltip title={!hasCriteria ? "Chưa có tiêu chí — hãy bóc & chốt tiêu chí trước"
          : vendorDocs(v.id).length === 0 ? "Nhà thầu chưa có hồ sơ HSDT" : ""}>
          <span>
            <Button size="small" type="primary" loading={evaluating === v.id}
              disabled={evaluating !== null || !hasCriteria || vendorDocs(v.id).length === 0}
              onClick={() => evalVendor(v.id)}>Chạy đánh giá</Button>
          </span>
        </Tooltip>
        <Button size="small" onClick={() => nav(`/packages/${id}/evaluation?vendor=${v.id}`)}>
          Xem kết quả</Button>
      </div>
      <DocTable docs={vendorDocs(v.id)} artifactTypes={artifactTypes}
        onChangeType={changeDocType} onDelete={deleteDoc} />
      <UploadDoc artifactTypes={artifactTypes} label="Tải hồ sơ nhà thầu"
        onUpload={(f, at) => uploadDoc(f, "HSDT", v.id, at)} />
    </div>
  );

  const items = [
    { key: "chung", label: "Tài liệu chung", children: chungTab },
    ...pkg.vendors.map((v) => ({ key: String(v.id), label: v.ten, children: vendorTab(v) })),
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end",
                    gap: 16, marginBottom: 20, flexWrap: "wrap" }}>
        <div>
          <span className="page-eyebrow">Gói thầu {pkg.ma_so} · <StatusTag status={pkg.trang_thai} /></span>
          <h1 className="page-title" style={{ marginBottom: 0 }}>{pkg.ten}</h1>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Button onClick={() => nav(`/packages/${id}/rubric`)}>Tiêu chí đánh giá</Button>
          <Button type="primary" onClick={() => nav(`/packages/${id}/evaluation`)}>Xem kết quả đánh giá</Button>
        </div>
      </div>

      <Card style={{ marginBottom: 16 }}>
        <Steps size="small" current={step} items={[
          { title: "Tải HSMT" }, { title: "Bóc & chốt tiêu chí" }, { title: "Tải HSDT nhà thầu" },
          { title: "Chạy đánh giá" }, { title: "Xem kết quả" },
        ]} />
      </Card>

      <Card styles={{ body: { paddingTop: 8 } }}>
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
      title={vendor ? "Sửa nhà thầu" : "Thêm nhà thầu"} destroyOnClose>
      <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 8 }}>
        <Input placeholder="Tên đầy đủ" value={ten} onChange={(e) => setTen(e.target.value)} />
        <Input placeholder="Tên viết tắt (khớp webform)" value={tt} onChange={(e) => setTt(e.target.value)} />
        <Select placeholder="Hình thức dự thầu (để trống = tự dò)" value={ht || undefined} allowClear
          onChange={(v) => setHt(v ?? "")} options={HINH_THUC_OPTS} />
      </div>
    </Modal>
  );
}
