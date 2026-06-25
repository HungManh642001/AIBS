import { Tag } from "antd";

const MAP: Record<string, { color: string; label: string }> = {
  khoi_tao: { color: "default", label: "Khởi tạo" },
  dang_xu_ly: { color: "processing", label: "Đang xử lý" },
  cho_review: { color: "warning", label: "Chờ review" },
  hoan_thanh: { color: "success", label: "Hoàn thành" },
};

export default function StatusTag({ status }: { status: string }) {
  const it = MAP[status] ?? { color: "default", label: status };
  return <Tag color={it.color}>{it.label}</Tag>;
}
