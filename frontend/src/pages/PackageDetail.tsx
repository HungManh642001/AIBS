import { useEffect, useState } from "react";
import { Button, Card, Select, Table, Upload, message } from "antd";
import { useNavigate, useParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import type { Package } from "../api/types";
import { ARTIFACT_TYPES } from "../api/types";
import StatusTag from "../components/StatusTag";

export default function PackageDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [pkg, setPkg] = useState<Package | null>(null);
  const [docs, setDocs] = useState<any[]>([]);
  const [loai, setLoai] = useState("HSMT");
  const [vendorId, setVendorId] = useState<number | undefined>();
  const [evaluating, setEvaluating] = useState(false);
  const [artifactType, setArtifactType] = useState<string | undefined>();

  const load = () => {
    api.get(`/packages/${id}`).then((r) => setPkg(unwrap<Package>(r)));
    api.get(`/packages/${id}/documents`).then((r) => setDocs(unwrap<any[]>(r)));
  };
  useEffect(load, [id]);

  const upload = async (file: File) => {
    const fd = new FormData();
    fd.append("file", file); fd.append("loai", loai);
    if (loai === "HSDT" && vendorId) fd.append("vendor_id", String(vendorId));
    if (loai === "HSDT" && artifactType) fd.append("artifact_type", artifactType);
    try {
      const res = await api.post(`/packages/${id}/documents`, fd);
      const doc = res.data.data;
      if (doc?.artifact_validation && doc.artifact_validation.match === false) {
        message.warning(`Nghi tải nhầm loại: ${doc.artifact_validation.note}`);
      } else {
        message.success("Đã tải lên & xử lý");
      }
      load();
    } catch (e: any) { message.error(e.message); }
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
          {loai === "HSDT" && (
            <Select placeholder="Loại hồ sơ" value={artifactType} onChange={setArtifactType}
              className="min-w-48" options={ARTIFACT_TYPES} />
          )}
          <Upload beforeUpload={upload} showUploadList={false}>
            <Button>Tải tài liệu</Button>
          </Upload>
          <Button onClick={() => nav(`/packages/${id}/de-cuong`)}>Đề cương chấm</Button>
          <Button type="primary" loading={evaluating} onClick={runEvaluate}>
            Chạy đánh giá AI</Button>
        </div>
      </Card>
      <Card title="Tài liệu">
        <Table rowKey="id" dataSource={docs} pagination={false} columns={[
          { title: "Loại", dataIndex: "loai" },
          { title: "Loại hồ sơ", dataIndex: "artifact_type" },
          { title: "Định dạng", dataIndex: "file_kind" },
          { title: "Trạng thái OCR", dataIndex: "trang_thai_ocr" },
        ]} />
      </Card>
    </div>
  );
}
