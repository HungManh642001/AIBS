import { useEffect, useMemo, useState } from "react";
import { Button, Card, Form, Input, InputNumber, Modal, Select, Table, message } from "antd";
import { useParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import type { EvalResult, ResultsPayload } from "../api/types";
import EvidenceCell from "../components/EvidenceCell";

export default function Evaluation() {
  const { id } = useParams();
  const [data, setData] = useState<ResultsPayload | null>(null);
  const [editing, setEditing] = useState<EvalResult | null>(null);
  const [form] = Form.useForm();

  const load = () => api.get(`/packages/${id}/results`)
    .then((r) => setData(unwrap<ResultsPayload>(r)));
  useEffect(() => { load(); }, [id]);

  const resultFor = (vid: number, cid: number) =>
    data?.vendors.find((v) => v.vendor_id === vid)?.results.find((x) => x.criteria_id === cid);

  const columns = useMemo(() => {
    if (!data) return [];
    return [
      { title: "Tiêu chí", dataIndex: "ten" },
      { title: "Nhóm", dataIndex: "nhom" },
      ...data.vendors.map((v) => ({
        title: v.ten,
        render: (_: unknown, c: { id: number }) => {
          const res = resultFor(v.vendor_id, c.id);
          return (
            <div className="flex items-center gap-2">
              <EvidenceCell result={res} />
              {res && <Button size="small" onClick={() => {
                setEditing(res);
                form.setFieldsValue({ ket_qua: res.ket_qua, diem_so: res.diem_so, ghi_chu: res.ghi_chu });
              }}>Sửa</Button>}
            </div>
          );
        },
      })),
    ];
  }, [data]);

  const saveOverride = async () => {
    if (!editing) return;
    const v = await form.validateFields();
    await api.put(`/evaluation/${editing.id}/override`, v);
    message.success("Đã ghi nhận override"); setEditing(null); load();
  };

  const genReport = async (loai: "word" | "excel") => {
    try {
      const res = unwrap<{ report_id: number }>(
        await api.post(`/packages/${id}/reports?loai=${loai}`));
      window.open(`http://localhost:8000/api/v1/reports/${res.report_id}/download`, "_blank");
    } catch (e: any) {
      message.error(e.message);
    }
  };

  if (!data) return null;
  return (
    <div className="space-y-4">
      <Card title="Bảng xếp hạng" extra={
        <div className="flex gap-2">
          <Button onClick={() => genReport("word")}>Xuất Word</Button>
          <Button onClick={() => genReport("excel")}>Xuất Excel</Button>
        </div>}>
        <Table rowKey="vendor_id" pagination={false} dataSource={data.ranking} columns={[
          { title: "Hạng", dataIndex: "rank", render: (r) => r ?? "Không hợp lệ" },
          { title: "Nhà thầu", dataIndex: "vendor_id",
            render: (vid) => data.vendors.find((v) => v.vendor_id === vid)?.ten },
          { title: "Giá đánh giá", dataIndex: "evaluated_price",
            render: (p: number) => p.toLocaleString("vi-VN") },
          { title: "Điểm KT", dataIndex: "technical_score",
            render: (s: number) => s.toFixed(1) },
        ]} />
      </Card>
      <Card title="Ma trận đánh giá theo tiêu chí">
        <Table rowKey="id" pagination={false} dataSource={data.criteria} columns={columns} scroll={{ x: true }} />
      </Card>
      <Modal title="Override kết quả AI" open={!!editing}
        onOk={saveOverride} onCancel={() => setEditing(null)}>
        <Form form={form} layout="vertical">
          <Form.Item name="ket_qua" label="Kết quả">
            <Select options={["PASS", "FAIL", "PARTIAL"].map((x) => ({ value: x, label: x }))} />
          </Form.Item>
          <Form.Item name="diem_so" label="Điểm"><InputNumber min={0} max={100} className="w-full" /></Form.Item>
          <Form.Item name="ghi_chu" label="Lý do (bắt buộc)" rules={[{ required: true }]}>
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
