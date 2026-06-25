import { useEffect, useState } from "react";
import { Button, Form, Input, InputNumber, Modal, Table, message } from "antd";
import { Link } from "react-router-dom";
import { api, unwrap } from "../api/client";
import type { Package } from "../api/types";
import StatusTag from "../components/StatusTag";

export default function Packages() {
  const [data, setData] = useState<Package[]>([]);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();

  const load = () => api.get("/packages").then((r) => setData(unwrap<Package[]>(r)));
  useEffect(() => { load(); }, []);

  const submit = async () => {
    const v = await form.validateFields();
    const vendors = (v.vendors ?? "").split(",").map((s: string) => s.trim()).filter(Boolean);
    try {
      await api.post("/packages", { ...v, vendors });
      message.success("Đã tạo gói thầu");
      setOpen(false); form.resetFields(); load();
    } catch (e: any) { message.error(e.message); }
  };

  return (
    <div>
      <div className="flex justify-between mb-4">
        <h2 className="text-xl font-semibold">Danh sách gói thầu</h2>
        <Button type="primary" onClick={() => setOpen(true)}>Tạo gói thầu</Button>
      </div>
      <Table rowKey="id" dataSource={data} columns={[
        { title: "Mã số", dataIndex: "ma_so" },
        { title: "Tên", dataIndex: "ten",
          render: (t, r) => <Link to={`/packages/${r.id}`}>{t}</Link> },
        { title: "Nhà thầu", render: (_, r) => r.vendors.length },
        { title: "Trạng thái", dataIndex: "trang_thai",
          render: (s) => <StatusTag status={s} /> },
      ]} />
      <Modal title="Tạo gói thầu" open={open} onOk={submit} onCancel={() => setOpen(false)}>
        <Form form={form} layout="vertical">
          <Form.Item name="ma_so" label="Mã số" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="ten" label="Tên gói thầu" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="gia_tri_uoc_tinh" label="Giá trị ước tính">
            <InputNumber className="w-full" min={0} /></Form.Item>
          <Form.Item name="vendors" label="Nhà thầu (phân tách bằng dấu phẩy)"><Input /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
