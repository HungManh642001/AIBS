import { useEffect, useState } from "react";
import { Button, Form, Input, InputNumber, Modal, Popconfirm, Table, message } from "antd";
import { PlusOutlined, DeleteOutlined } from "@ant-design/icons";
import { Link } from "react-router-dom";
import { api, unwrap } from "../api/client";
import type { Package } from "../api/types";
import StatusTag from "../components/StatusTag";

export default function Packages() {
  const [data, setData] = useState<Package[]>([]);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();

  const load = () =>
    api.get("/packages").then((r) => setData(unwrap<Package[]>(r))).catch(() => {});

  useEffect(() => { load(); }, []);

  const del = async (id: number) => {
    try {
      await api.delete(`/packages/${id}`);
      message.success("Đã xóa gói thầu");
      load();
    } catch (e: any) {
      message.error(e.message);
    }
  };

  const submit = async () => {
    const v = await form.validateFields();
    const vendors = (v.vendors ?? "").split(",").map((s: string) => s.trim()).filter(Boolean);
    try {
      await api.post("/packages", { ...v, vendors });
      message.success("Đã tạo gói thầu");
      setOpen(false);
      form.resetFields();
      load();
    } catch (e: any) {
      message.error(e.message);
    }
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 20 }}>
        <div>
          <span className="page-eyebrow">Quản lý</span>
          <h1 className="page-title" style={{ marginBottom: 0 }}>Gói thầu</h1>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>
          Tạo gói thầu
        </Button>
      </div>

      <div style={{ background: "var(--paper)", border: "1px solid var(--line)", borderRadius: 8, overflow: "hidden" }}>
        <Table
          rowKey="id"
          dataSource={data}
          pagination={{ pageSize: 20, showSizeChanger: false }}
          columns={[
            {
              title: "Mã số",
              dataIndex: "ma_so",
              width: 130,
              render: (v) => <span className="mono" style={{ fontSize: 13 }}>{v}</span>,
            },
            {
              title: "Tên gói thầu",
              dataIndex: "ten",
              render: (t, r) => (
                <Link to={`/packages/${r.id}`} style={{ color: "var(--teal)", fontWeight: 600 }}>
                  {t}
                </Link>
              ),
            },
            {
              title: "Nhà thầu",
              width: 100,
              render: (_, r) => (
                <span className="mono" style={{ color: "var(--ink-muted)" }}>{r.vendors.length}</span>
              ),
            },
            {
              title: "Trạng thái",
              dataIndex: "trang_thai",
              width: 150,
              render: (s) => <StatusTag status={s} />,
            },
            {
              title: "",
              width: 90,
              render: (_, r) => (
                <Popconfirm
                  title="Xóa gói thầu này?"
                  description="Xóa toàn bộ tài liệu, tiêu chí và kết quả của gói."
                  okText="Xóa" cancelText="Hủy" okButtonProps={{ danger: true }}
                  onConfirm={() => del(r.id)}
                >
                  <Button danger size="small" icon={<DeleteOutlined />}>Xóa</Button>
                </Popconfirm>
              ),
            },
          ]}
        />
      </div>

      <Modal
        title="Tạo gói thầu mới"
        open={open}
        onOk={submit}
        onCancel={() => setOpen(false)}
        okText="Tạo"
        cancelText="Hủy"
        width={480}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="ma_so" label="Mã số" rules={[{ required: true, message: "Nhập mã số" }]}>
            <Input placeholder="Vd: GT-2026-001" />
          </Form.Item>
          <Form.Item name="ten" label="Tên gói thầu" rules={[{ required: true, message: "Nhập tên" }]}>
            <Input placeholder="Tên đầy đủ của gói thầu" />
          </Form.Item>
          <Form.Item name="gia_tri_uoc_tinh" label="Giá trị ước tính (VNĐ)">
            <InputNumber
              style={{ width: "100%" }}
              min={0}
              formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ",")}
              placeholder="0"
            />
          </Form.Item>
          <Form.Item name="vendors" label="Nhà thầu (phân cách bằng dấu phẩy)">
            <Input placeholder="Công ty A, Công ty B" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
