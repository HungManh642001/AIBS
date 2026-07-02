import { useEffect, useState } from "react";
import { Button, Card, Input, Select, Table, Tag, message } from "antd";
import { useParams, useNavigate } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { ARTIFACT_TYPES, type RubricCriteria } from "../api/types";

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

  const setNoiDung = (ci: number, ni: number, key: string, val: unknown) => {
    setCriteria((prev) => {
      const next = structuredClone(prev);
      (next[ci].noi_dung_can_kiem_tra[ni] as any)[key] = val;
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
        <Card key={ci} title={c.ten} style={{ marginBottom: 12 }} extra={
          <span>
            <Tag color="blue">{c.nhom}</Tag>
            {c.tien_quyet && <Tag color="red">Tiên quyết</Tag>}
            {c.hsdt_can_kiem_tra?.map((a) => <Tag key={a}>{a}</Tag>)}
          </span>}>
          <p style={{ color: "#666", marginTop: 0 }}>Yêu cầu gốc (HSMT): {c.yeu_cau_goc}</p>
          <Table rowKey={(_, i) => String(i)} pagination={false} dataSource={c.noi_dung_can_kiem_tra}
            columns={[
              { title: "Nội dung kiểm tra (HSDT)", dataIndex: "noi_dung_kiem_tra",
                render: (t, _n, ni) => <Input value={t} onChange={(e) => setNoiDung(ci, ni, "noi_dung_kiem_tra", e.target.value)} /> },
              { title: "Hồ sơ", dataIndex: "hsdt_kiem_tra",
                render: (t, _n, ni) => <Select value={t} options={ARTIFACT_TYPES} className="min-w-44"
                  onChange={(v) => setNoiDung(ci, ni, "hsdt_kiem_tra", v)} /> },
              { title: "Yêu cầu", dataIndex: "yeu_cau",
                render: (t, _n, ni) => <Input value={t} onChange={(e) => setNoiDung(ci, ni, "yeu_cau", e.target.value)} /> },
              { title: "Thông tin bổ sung (chuẩn HSMT)", dataIndex: "thong_tin_bo_sung",
                render: (t, _n, ni) => <Input value={t} onChange={(e) => setNoiDung(ci, ni, "thong_tin_bo_sung", e.target.value)} /> },
              { title: "Nguồn", dataIndex: "nguon",
                render: (t, _n, ni) => <Input value={t} className="min-w-28"
                  onChange={(e) => setNoiDung(ci, ni, "nguon", e.target.value)} /> },
              { title: "Cần soi", dataIndex: "can_review",
                render: (t: boolean) => t ? <Tag color="orange">Cần soi</Tag> : <Tag color="green">OK</Tag> },
            ]} />
        </Card>
      ))}
    </div>
  );
}
