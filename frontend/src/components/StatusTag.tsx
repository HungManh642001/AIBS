const MAP: Record<string, { bg: string; color: string; label: string }> = {
  khoi_tao:   { bg: "#F0F0F0", color: "#666",          label: "Khởi tạo" },
  dang_xu_ly: { bg: "#FEF4E3", color: "#C77D11",       label: "Đang xử lý" },
  cho_review: { bg: "#E6F4F2", color: "#0F6E62",       label: "Chờ review" },
  hoan_thanh: { bg: "#EAF6EF", color: "#2E7D54",       label: "Hoàn thành" },
};

export default function StatusTag({ status }: { status: string }) {
  const it = MAP[status] ?? { bg: "#F0F0F0", color: "#888", label: status };
  return (
    <span style={{
      display: "inline-block",
      padding: "2px 9px",
      borderRadius: 4,
      fontSize: 11,
      fontWeight: 600,
      letterSpacing: "0.04em",
      textTransform: "uppercase" as const,
      background: it.bg,
      color: it.color,
    }}>
      {it.label}
    </span>
  );
}
