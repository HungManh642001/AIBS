import { Tag, Tooltip } from "antd";
import type { EvalResult } from "../api/types";

const COLOR: Record<string, string> = { PASS: "green", FAIL: "red", PARTIAL: "orange" };

export default function EvidenceCell({ result }: { result?: EvalResult }) {
  if (!result) return <span className="text-gray-400">—</span>;
  return (
    <Tooltip title={`${result.dan_chung} [trang ${result.so_trang.join(", ")}]`}>
      <div>
        <Tag color={COLOR[result.ket_qua] ?? "default"}>{result.ket_qua}</Tag>
        <span>{result.diem_so}</span>
        {result.overridden && <Tag color="purple" className="ml-1">override</Tag>}
      </div>
    </Tooltip>
  );
}
