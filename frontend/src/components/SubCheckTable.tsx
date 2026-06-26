import { useState } from "react";
import { Button, Input, Modal, Select, Table, message } from "antd";
import { EditOutlined } from "@ant-design/icons";
import { api } from "../api/client";
import type { SubResult } from "../api/types";

function ResultPill({ result }: { result: string }) {
  const cls = ["PASS", "FAIL", "PARTIAL"].includes(result) ? result : "default";
  return <span className={`verdict-result-pill ${cls}`}>{result}</span>;
}

function SourceChip({ model }: { model: string }) {
  if (!model) return null;
  const cls = model === "mock" ? "mock" : model.startsWith("python") ? "python" : "real";
  return <span className={`source-chip ${cls}`}>{model}</span>;
}

export default function SubCheckTable({
  subs,
  onChanged,
}: {
  subs: SubResult[];
  onChanged: () => void;
}) {
  const [editing, setEditing] = useState<SubResult | null>(null);
  const [ketQua, setKetQua] = useState("FAIL");
  const [ghiChu, setGhiChu] = useState("");

  const save = async () => {
    if (!editing) return;
    try {
      await api.put(`/evaluation/sub-check-result/${editing.id}/override`, {
        ket_qua: ketQua,
        ghi_chu: ghiChu,
      });
      message.success("Đã điều chỉnh kết quả");
      setEditing(null);
      onChanged();
    } catch (e: any) {
      message.error(e.message);
    }
  };

  return (
    <>
      <Table<SubResult>
        rowKey="id"
        pagination={false}
        size="small"
        dataSource={subs}
        style={{ fontSize: 13 }}
        columns={[
          {
            title: "Điểm kiểm",
            dataIndex: "sub_check_ten",
            width: "22%",
            render: (v) => <span style={{ fontWeight: 500 }}>{v}</span>,
          },
          {
            title: "Kết quả",
            dataIndex: "result",
            width: 130,
            render: (r: string, s) => (
              <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                <ResultPill result={r} />
                {s.overridden && (
                  <span style={{
                    fontSize: 10, fontWeight: 600, padding: "1px 6px", borderRadius: 3,
                    background: "#EDE9FE", color: "#6D28D9", border: "1px solid #C4B5FD",
                  }}>
                    override
                  </span>
                )}
              </div>
            ),
          },
          {
            title: "Dẫn chứng",
            dataIndex: "evidence",
            render: (v) => (
              <span style={{ color: "var(--ink-muted)", fontSize: 12, lineHeight: 1.5 }}>{v}</span>
            ),
          },
          {
            title: "Trang",
            dataIndex: "page_ref",
            width: 80,
            render: (p: number[]) => (
              <span className="mono" style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                {p.length ? p.join(", ") : "—"}
              </span>
            ),
          },
          {
            title: "Nguồn AI",
            dataIndex: "ai_model",
            width: 110,
            render: (m) => <SourceChip model={m ?? ""} />,
          },
          {
            title: "",
            width: 56,
            render: (_t, s) => (
              <Button
                size="small"
                icon={<EditOutlined />}
                onClick={() => { setEditing(s); setKetQua(s.result); setGhiChu(""); }}
              />
            ),
          },
        ]}
      />

      <Modal
        title="Điều chỉnh kết quả"
        open={!!editing}
        onOk={save}
        onCancel={() => setEditing(null)}
        okText="Lưu"
        cancelText="Hủy"
        width={400}
      >
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 12, color: "var(--ink-muted)", marginBottom: 6 }}>Điểm kiểm</div>
          <div style={{ fontWeight: 600 }}>{editing?.sub_check_ten}</div>
        </div>
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 12, color: "var(--ink-muted)", marginBottom: 6 }}>Kết quả mới</div>
          <Select
            value={ketQua}
            onChange={setKetQua}
            style={{ width: "100%" }}
            options={["PASS", "FAIL", "PARTIAL"].map((x) => ({ value: x, label: x }))}
          />
        </div>
        <div>
          <div style={{ fontSize: 12, color: "var(--ink-muted)", marginBottom: 6 }}>Lý do điều chỉnh</div>
          <Input.TextArea
            placeholder="Ghi rõ lý do..."
            value={ghiChu}
            onChange={(e) => setGhiChu(e.target.value)}
            rows={3}
          />
        </div>
      </Modal>
    </>
  );
}
