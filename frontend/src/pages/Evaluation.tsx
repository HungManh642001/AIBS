import { useEffect, useState } from "react";
import { Button, Card, message } from "antd";
import { useParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import type { ResultsBreakdown } from "../api/types";
import SubCheckTable from "../components/SubCheckTable";

export default function Evaluation() {
  const { id } = useParams();
  const [data, setData] = useState<ResultsBreakdown | null>(null);

  const load = () => api.get(`/packages/${id}/results`)
    .then((r) => setData(unwrap<ResultsBreakdown>(r)));
  useEffect(() => { load(); }, [id]);

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
      <div className="flex gap-2 justify-end">
        <Button onClick={() => genReport("word")}>Xuất Word</Button>
        <Button onClick={() => genReport("excel")}>Xuất Excel</Button>
      </div>
      {data.vendors.map((v: any) => (
        <Card key={v.vendor_id} title={`Nhà thầu: ${v.ten}`}>
          {v.criteria.map((c: any) => (
            <Card key={c.criteria_id} type="inner" className="mb-3"
              title={`${c.criteria_ten} — ${c.result ?? "—"} (${c.score})`}>
              <SubCheckTable subs={c.sub_results} onChanged={load} />
            </Card>
          ))}
        </Card>
      ))}
    </div>
  );
}
