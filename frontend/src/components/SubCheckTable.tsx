import { useState } from "react";
import { Button, Input, Modal, Select, Table, Tag, message } from "antd";
import { api } from "../api/client";
import type { SubResult } from "../api/types";

const COLOR: Record<string, string> = { PASS: "green", FAIL: "red", PARTIAL: "orange" };

export default function SubCheckTable({ subs, onChanged }: { subs: SubResult[]; onChanged: () => void }) {
  const [editing, setEditing] = useState<SubResult | null>(null);
  const [ketQua, setKetQua] = useState("FAIL");
  const [ghiChu, setGhiChu] = useState("");

  const save = async () => {
    if (!editing) return;
    try {
      await api.put(`/evaluation/sub-check-result/${editing.id}/override`, { ket_qua: ketQua, ghi_chu: ghiChu });
      message.success("Đã override"); setEditing(null); onChanged();
    } catch (e: any) { message.error(e.message); }
  };

  return (
    <>
      <Table<SubResult> rowKey="id" pagination={false} size="small" dataSource={subs} columns={[
        { title: "Điểm kiểm", dataIndex: "sub_check_ten" },
        { title: "Kết quả", dataIndex: "result",
          render: (r: string, s) => <><Tag color={COLOR[r] ?? "default"}>{r}</Tag>{s.overridden && <Tag color="purple">override</Tag>}</> },
        { title: "Dẫn chứng", dataIndex: "evidence" },
        { title: "Trang", dataIndex: "page_ref", render: (p: number[]) => p.join(", ") },
        { title: "", render: (_t, s) => <Button size="small" onClick={() => { setEditing(s); setKetQua(s.result); setGhiChu(""); }}>Sửa</Button> },
      ]} />
      <Modal title="Điều chỉnh kết quả sub-check" open={!!editing} onOk={save} onCancel={() => setEditing(null)}>
        <Select value={ketQua} onChange={setKetQua} className="w-full mb-2"
          options={["PASS", "FAIL", "PARTIAL"].map((x) => ({ value: x, label: x }))} />
        <Input.TextArea placeholder="Lý do" value={ghiChu} onChange={(e) => setGhiChu(e.target.value)} rows={3} />
      </Modal>
    </>
  );
}
