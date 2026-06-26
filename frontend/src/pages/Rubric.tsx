import { useEffect, useState } from "react";
import { Button, Card, Input, Select, Table, Tag, message } from "antd";
import { useParams, useNavigate } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { ARTIFACT_TYPES, type RubricCriteria } from "../api/types";

const CHECK_TYPES = ["presence", "form_match", "signature_stamp", "authority",
  "value_threshold", "date_validity", "quantity_match", "semantic_match"]
  .map((v) => ({ value: v, label: v }));

export default function Rubric() {
  const { id } = useParams();
  const nav = useNavigate();
  const [criteria, setCriteria] = useState<RubricCriteria[]>([]);

  const load = () => api.get(`/packages/${id}/rubric`)
    .then((r) => setCriteria(unwrap<{ criteria: RubricCriteria[] }>(r).criteria));
  useEffect(() => { load(); }, [id]);

  const extract = async () => {
    try {
      setCriteria(unwrap<{ criteria: RubricCriteria[] }>(await api.post(`/packages/${id}/rubric`)).criteria);
      message.success("Đã bóc tách tiêu chí đánh giá từ HSMT");
    } catch (e: any) { message.error(e.message); }
  };
  const save = async () => {
    try {
      await api.put(`/packages/${id}/rubric`, { criteria });
      message.success("Đã lưu tiêu chí đánh giá");
    } catch (e: any) { message.error(e.message); }
  };
  const confirm = async () => {
    try {
      await api.put(`/packages/${id}/rubric`, { criteria });
      await api.post(`/packages/${id}/rubric/confirm`);
      message.success("Đã chốt tiêu chí đánh giá");
      nav(`/packages/${id}`);
    } catch (e: any) { message.error(e.message); }
  };

  const setSub = (ci: number, si: number, key: string, val: unknown) => {
    setCriteria((prev) => {
      const next = structuredClone(prev);
      (next[ci].sub_checks[si] as any)[key] = val;
      return next;
    });
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 20 }}>
        <div>
          <span className="page-eyebrow">Barem chấm thầu</span>
          <h1 className="page-title" style={{ marginBottom: 0 }}>Tiêu chí đánh giá</h1>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Button onClick={extract}>Bóc tách từ HSMT</Button>
          <Button onClick={save}>Lưu</Button>
          <Button type="primary" onClick={confirm}>Chốt tiêu chí</Button>
        </div>
      </div>

      {criteria.map((c, ci) => (
        <Card key={ci} title={`${c.ten}`} style={{ marginBottom: 12 }} extra={
          <span>Loại HS: {c.required_artifacts.map((a) => <Tag key={a}>{a}</Tag>)}</span>}>
          <Table rowKey={(_, i) => String(i)} pagination={false} dataSource={c.sub_checks}
            columns={[
              { title: "Điểm kiểm", dataIndex: "ten",
                render: (t, _s, si) => <Input value={t} onChange={(e) => setSub(ci, si, "ten", e.target.value)} /> },
              { title: "Loại kiểm", dataIndex: "check_type",
                render: (t, _s, si) => <Select value={t} options={CHECK_TYPES} className="min-w-40"
                  onChange={(v) => setSub(ci, si, "check_type", v)} /> },
              { title: "Loại hồ sơ", dataIndex: "required_artifact",
                render: (t, _s, si) => <Select value={t} options={ARTIFACT_TYPES} className="min-w-44"
                  onChange={(v) => setSub(ci, si, "required_artifact", v)} /> },
              { title: "Ngưỡng (JSON)", dataIndex: "thong_so",
                render: (t, _s, si) => <Input value={JSON.stringify(t)}
                  onChange={(e) => { try { setSub(ci, si, "thong_so", JSON.parse(e.target.value)); } catch { /* giữ nguyên */ } }} /> },
              { title: "Bắt buộc", dataIndex: "blocking",
                render: (t: boolean, _s, si) => <Select value={t ? "1" : "0"}
                  options={[{ value: "1", label: "Có" }, { value: "0", label: "Không" }]}
                  onChange={(v) => setSub(ci, si, "blocking", v === "1")} /> },
            ]} />
        </Card>
      ))}
    </div>
  );
}
