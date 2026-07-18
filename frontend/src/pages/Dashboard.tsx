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
      {/* Không đặt eyebrow "ABES" ở đây: logo sidebar đã nói đúng câu đó rồi. Tiêu đề dùng chung
          một từ với breadcrumb và menu ("Tổng quan") để người dùng nhận ra mình đang ở đâu. */}
      <h1 className="page-title">Tổng quan</h1>

      <Loader loading={loading} error={err} onRetry={load}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "var(--sp-4)", marginBottom: "var(--sp-6)" }}>
          <StatCard label="Tất cả gói thầu" value={pkgs.length} accent="teal" to="/packages" />
          <StatCard label="Đang xử lý" value={byStatus("dang_xu_ly")} accent="partial" to="/packages?trang_thai=dang_xu_ly" />
          <StatCard label="Chờ rà soát" value={byStatus("cho_review")} accent="ink" to="/packages?trang_thai=cho_review" />
          <StatCard label="Hoàn thành" value={byStatus("hoan_thanh")} accent="pass" to="/packages?trang_thai=hoan_thanh" />
        </div>

        <span className="page-eyebrow">Gói thầu gần đây</span>
        <div style={{ background: "var(--paper)", border: "1px solid var(--line)", borderRadius: 8,
                      overflow: "hidden", marginTop: "var(--sp-2)" }}>
          {pkgs.length === 0
            ? <div style={{ padding: "var(--sp-5)", color: "var(--ink-muted)", textAlign: "center" }}>
                Chưa có gói thầu nào. Sang mục <Link to="/packages" style={{ color: "var(--teal)" }}>Gói thầu</Link> để tạo gói đầu tiên.
              </div>
            : pkgs.slice(0, 8).map((p) => (
              <Link key={p.id} to={`/packages/${p.id}`}
                style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
                         gap: "var(--sp-3)", padding: "var(--sp-3) var(--sp-4)", borderBottom: "1px solid var(--line)",
                         textDecoration: "none", color: "inherit" }}>
                <span>
                  <span className="mono" style={{ fontSize: "var(--fs-label)", color: "var(--ink-muted)", marginRight: "var(--sp-3)" }}>{p.ma_so}</span>
                  <span style={{ fontWeight: 600 }}>{p.ten}</span>
                </span>
                <span style={{ display: "flex", alignItems: "center", gap: "var(--sp-3)" }}>
                  <span style={{ fontSize: "var(--fs-label)", color: "var(--ink-muted)" }}>{p.vendors.length} nhà thầu</span>
                  <StatusTag status={p.trang_thai} />
                </span>
              </Link>
            ))}
        </div>
      </Loader>
    </div>
  );
}
