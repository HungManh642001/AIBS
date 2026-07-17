import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, unwrap } from "../api/client";
import type { Package } from "../api/types";
import StatusTag from "../components/StatusTag";
import Loader from "../components/Loader";

interface StatCardProps {
  label: string;
  value: number;
  accent: "teal" | "pass" | "partial" | "ink";
  to: string;
}

function StatCard({ label, value, accent, to }: StatCardProps) {
  return (
    <Link to={to} className={`stat-card ${accent}`} style={{ display: "block", textDecoration: "none" }}>
      <div className="stat-number">{value}</div>
      <div className="stat-label">{label}</div>
    </Link>
  );
}

export default function Dashboard() {
  const [pkgs, setPkgs] = useState<Package[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const load = () => {
    setLoading(true); setErr(null);
    api.get("/packages").then((r) => setPkgs(unwrap<Package[]>(r)))
      .catch((e) => setErr(e.message)).finally(() => setLoading(false));
  };
  useEffect(load, []);

  const byStatus = (s: string) => pkgs.filter((p) => p.trang_thai === s).length;

  return (
    <div>
      <span className="page-eyebrow">Tổng quan</span>
      <h1 className="page-title">Trạng thái hệ thống</h1>

      <Loader loading={loading} error={err} onRetry={load}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginBottom: 32 }}>
          <StatCard label="Tổng gói thầu" value={pkgs.length} accent="teal" to="/packages" />
          <StatCard label="Đang xử lý" value={byStatus("dang_xu_ly")} accent="partial" to="/packages?trang_thai=dang_xu_ly" />
          <StatCard label="Chờ review" value={byStatus("cho_review")} accent="ink" to="/packages?trang_thai=cho_review" />
          <StatCard label="Hoàn thành" value={byStatus("hoan_thanh")} accent="pass" to="/packages?trang_thai=hoan_thanh" />
        </div>

        <span className="page-eyebrow">Gói thầu</span>
        <div style={{ background: "var(--paper)", border: "1px solid var(--line)", borderRadius: 8,
                      overflow: "hidden", marginTop: 8 }}>
          {pkgs.length === 0
            ? <div style={{ padding: "24px", color: "var(--ink-muted)", textAlign: "center" }}>Chưa có gói thầu nào.</div>
            : pkgs.slice(0, 8).map((p) => (
              <Link key={p.id} to={`/packages/${p.id}`}
                style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
                         gap: 12, padding: "12px 16px", borderBottom: "1px solid var(--line)",
                         textDecoration: "none", color: "inherit" }}>
                <span>
                  <span className="mono" style={{ fontSize: 12, color: "var(--ink-muted)", marginRight: 10 }}>{p.ma_so}</span>
                  <span style={{ fontWeight: 600 }}>{p.ten}</span>
                </span>
                <span style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>{p.vendors.length} nhà thầu</span>
                  <StatusTag status={p.trang_thai} />
                </span>
              </Link>
            ))}
        </div>
      </Loader>
    </div>
  );
}
