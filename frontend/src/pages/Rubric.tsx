import { useEffect, useState } from "react";
import { Button, Card, Checkbox, Input, Select, Table, Tag, message } from "antd";
import { ArrowLeftOutlined } from "@ant-design/icons";
import Loader from "../components/Loader";

const { TextArea } = Input;
const AUTO = { minRows: 1, maxRows: 6 } as const;
import { useParams, useNavigate } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { useArtifactTypes, useArtifactLabel, NHOM_LABEL } from "../api/artifacts";
import type { RubricCriteria } from "../api/types";

export default function Rubric() {
  const { id } = useParams();
  const nav = useNavigate();
  const [criteria, setCriteria] = useState<RubricCriteria[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [extracting, setExtracting] = useState(false);
  const artifactTypes = useArtifactTypes();
  const nhan = useArtifactLabel();

  const load = () => {
    setLoading(true); setErr(null);
    api.get(`/packages/${id}/rubric`)
      .then((r) => setCriteria(unwrap<{ criteria: RubricCriteria[] }>(r).criteria))
      .catch((e) => setErr(e.message)).finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, [id]);

  const extract = async () => {
    setExtracting(true);
    message.loading({ content: "Đang đọc HSMT và trích tiêu chí — có thể mất vài phút…", key: "extract", duration: 0 });
    try {
      setCriteria(unwrap<{ criteria: RubricCriteria[] }>(await api.post(`/packages/${id}/rubric`)).criteria);
      message.success({ content: "Đã trích tiêu chí từ HSMT", key: "extract" });
    } catch (e: any) { message.error({ content: e.message, key: "extract" }); }
    finally { setExtracting(false); }
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
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
                    gap: "var(--sp-4)", marginBottom: "var(--sp-5)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)" }}>
          <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => nav(`/packages/${id}`)}
            style={{ paddingLeft: 0 }} aria-label="Quay lại gói thầu" />
          <h1 className="page-title" style={{ marginBottom: 0 }}>Tiêu chuẩn đánh giá</h1>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Button loading={extracting} onClick={extract}>Trích tiêu chí từ HSMT</Button>
          <Button onClick={save} disabled={criteria.length === 0}>Lưu</Button>
          <Button type="primary" onClick={confirm} disabled={criteria.length === 0}>Chốt tiêu chí</Button>
        </div>
      </div>

      <Loader loading={loading} error={err} onRetry={load}>
      {criteria.length === 0 && (
        <div style={{ textAlign: "center", padding: "48px 0", background: "var(--paper)",
                      border: "1px solid var(--line)", borderRadius: 8, color: "var(--ink-muted)" }}>
          Chưa có tiêu chí nào. Tải HSMT lên ở trang gói thầu, rồi bấm “Trích tiêu chí từ HSMT”.
        </div>
      )}
      {criteria.map((c, ci) => (
        <Card key={ci} title={c.ten} style={{ marginBottom: 12 }} extra={
          <span>
            <Tag color="blue">{NHOM_LABEL[c.nhom] ?? c.nhom}</Tag>
            {c.tien_quyet && <Tag color="red">Tiên quyết</Tag>}
            {c.hsdt_can_kiem_tra?.map((a) => <Tag key={a}>{nhan(a)}</Tag>)}
          </span>}>
          <p style={{ color: "var(--ink-muted)", marginTop: 0 }}>
            <b style={{ color: "var(--ink)" }}>Nguyên văn HSMT:</b> {c.yeu_cau_goc}
          </p>
          <Table rowKey={(_, i) => String(i)} pagination={false} dataSource={c.noi_dung_can_kiem_tra}
            scroll={{ x: 1080 }}
            columns={[
              { title: "Nội dung kiểm tra", dataIndex: "noi_dung_kiem_tra", width: 210,
                render: (t, _n, ni) => <TextArea autoSize={AUTO} value={t}
                  onChange={(e) => setNoiDung(ci, ni, "noi_dung_kiem_tra", e.target.value)} /> },
              { title: "Đối chiếu hồ sơ", dataIndex: "hsdt_kiem_tra", width: 175,
                render: (t, _n, ni) => <Select value={t} options={artifactTypes} style={{ width: "100%" }}
                  onChange={(v) => setNoiDung(ci, ni, "hsdt_kiem_tra", v)} /> },
              { title: "Yêu cầu", dataIndex: "yeu_cau", width: 210,
                render: (t, _n, ni) => <TextArea autoSize={AUTO} value={t}
                  onChange={(e) => setNoiDung(ci, ni, "yeu_cau", e.target.value)} /> },
              // Nguồn gộp vào ô chuẩn: nó là XUẤT XỨ của chuẩn này, tách cột riêng vừa tốn 120px
              // vừa làm số điều khoản bị xén ("E-CDNT" mất phần "11.1").
              { title: "Chuẩn cụ thể theo HSMT", dataIndex: "thong_tin_bo_sung", width: 260,
                render: (t, _n, ni) => (
                  <div>
                    <TextArea autoSize={AUTO} value={t}
                      placeholder="HSMT không nêu mức cụ thể"
                      onChange={(e) => setNoiDung(ci, ni, "thong_tin_bo_sung", e.target.value)} />
                    <Input size="small" value={_n.nguon} placeholder="điều khoản nguồn"
                      style={{ marginTop: 4, fontSize: "var(--fs-label)" }} className="mono"
                      onChange={(e) => setNoiDung(ci, ni, "nguon", e.target.value)} />
                  </div>
                ) },
              { title: "Áp dụng với", dataIndex: "ap_dung", width: 150,
                render: (t: string, _n, ni) => <Select value={t || ""} style={{ width: "100%" }}
                  onChange={(v) => setNoiDung(ci, ni, "ap_dung", v)}
                  options={[
                    { value: "", label: "Mọi nhà thầu" },
                    { value: "lien_danh", label: "Chỉ liên danh" },
                    { value: "doc_lap", label: "Chỉ độc lập" },
                  ]} /> },
              // Ô tick không cần nhãn riêng — tiêu đề cột đã nói đúng việc đó, nhãn lặp lại chỉ
              // tốn chỗ và bị xuống dòng trong cột hẹp.
              { title: "Cần chuyên gia kiểm tra", dataIndex: "can_review", width: 175,
                render: (t: boolean, _n, ni) => (
                  <div>
                    <Checkbox checked={t}
                      onChange={(e) => setNoiDung(ci, ni, "can_review", e.target.checked)} />
                    {t && _n.can_lam_ro && (
                      <div style={{ fontSize: "var(--fs-label)", color: "var(--partial)", marginTop: 4 }}>
                        {_n.can_lam_ro}
                      </div>
                    )}
                  </div>
                ) },
            ]} />
        </Card>
      ))}
      </Loader>
    </div>
  );
}
