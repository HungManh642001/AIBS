import { useEffect, useState } from "react";
import { Button, Card, Select, Table, Upload, message } from "antd";
import { useNavigate, useParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import type { Package } from "../api/types";
import StatusTag from "../components/StatusTag";

export default function PackageDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [pkg, setPkg] = useState<Package | null>(null);
  const [docs, setDocs] = useState<any[]>([]);
  const [loai, setLoai] = useState("HSMT");
  const [vendorId, setVendorId] = useState<number | undefined>();
  const [evaluating, setEvaluating] = useState(false);

  const load = () => {
    api.get(`/packages/${id}`).then((r) => setPkg(unwrap<Package>(r)));
    api.get(`/packages/${id}/documents`).then((r) => setDocs(unwrap<any[]>(r)));
  };
  useEffect(load, [id]);

  const upload = async (file: File) => {
    const fd = new FormData();
    fd.append("file", file); fd.append("loai", loai);
    if (loai === "HSDT" && vendorId) fd.append("vendor_id", String(vendorId));
    await api.post(`/packages/${id}/documents`, fd);
    message.success("Đã tải lên & xử lý"); load();
    return false;
  };

  const runEvaluate = async () => {
    setEvaluating(true);
    try {
      await api.post(`/packages/${id}/evaluate`);
      message.success("Đánh giá hoàn tất");
      nav(`/packages/${id}/evaluation`);
    } catch (e: any) { message.error(e.message); }
    finally { setEvaluating(false); }
  };

  if (!pkg) return null;
  return (
    <div className="space-y-4">
      <Card title={`${pkg.ma_so} — ${pkg.ten}`} extra={<StatusTag status={pkg.trang_thai} />}>
        <div className="flex gap-3 items-center">
          <Select value={loai} onChange={setLoai} options={[
            { value: "HSMT", label: "HSMT" }, { value: "HSDT", label: "HSDT" }]} />
          {loai === "HSDT" && (
            <Select placeholder="Chọn nhà thầu" value={vendorId} onChange={setVendorId}
              className="min-w-48"
              options={pkg.vendors.map((v) => ({ value: v.id, label: v.ten }))} />
          )}
          <Upload beforeUpload={upload} showUploadList={false}>
            <Button>Tải tài liệu</Button>
          </Upload>
          <Button type="primary" loading={evaluating} onClick={runEvaluate}>
            Chạy đánh giá AI</Button>
        </div>
      </Card>
      <Card title="Tài liệu">
        <Table rowKey="id" dataSource={docs} pagination={false} columns={[
          { title: "Loại", dataIndex: "loai" },
          { title: "Định dạng", dataIndex: "file_kind" },
          { title: "Trạng thái OCR", dataIndex: "trang_thai_ocr" },
        ]} />
      </Card>
    </div>
  );
}
