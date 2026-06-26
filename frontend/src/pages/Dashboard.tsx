import { useEffect, useState } from "react";
import { api, unwrap } from "../api/client";
import type { Package } from "../api/types";

interface StatCardProps {
  label: string;
  value: number;
  accent: "teal" | "pass" | "partial" | "ink";
}

function StatCard({ label, value, accent }: StatCardProps) {
  return (
    <div className={`stat-card ${accent}`}>
      <div className="stat-number">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

export default function Dashboard() {
  const [pkgs, setPkgs] = useState<Package[]>([]);

  useEffect(() => {
    api.get("/packages").then((r) => setPkgs(unwrap<Package[]>(r))).catch(() => {});
  }, []);

  const byStatus = (s: string) => pkgs.filter((p) => p.trang_thai === s).length;

  return (
    <div>
      <span className="page-eyebrow">Tổng quan</span>
      <h1 className="page-title">Trạng thái hệ thống</h1>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginBottom: 32 }}>
        <StatCard label="Tổng gói thầu" value={pkgs.length} accent="teal" />
        <StatCard label="Đang xử lý" value={byStatus("dang_xu_ly")} accent="partial" />
        <StatCard label="Chờ review" value={byStatus("cho_review")} accent="ink" />
        <StatCard label="Hoàn thành" value={byStatus("hoan_thanh")} accent="pass" />
      </div>
    </div>
  );
}
