import { useEffect, useState } from "react";
import { Breadcrumb, Layout, Menu, Tooltip } from "antd";
import { BarChartOutlined, FolderOpenOutlined } from "@ant-design/icons";
import { Link, Route, Routes, useLocation } from "react-router-dom";
import { api, unwrap } from "./api/client";
import Dashboard from "./pages/Dashboard";
import Packages from "./pages/Packages";
import PackageDetail from "./pages/PackageDetail";
import Evaluation from "./pages/Evaluation";
import Rubric from "./pages/Rubric";

interface HealthData {
  ai_mode: "mock" | "real";
  ai_model: string;
}

interface PkgBrief { id: number; ma_so: string; ten: string; trang_thai: string }

const TRANG_THAI_LABEL: Record<string, string> = {
  khoi_tao: "Khởi tạo", dang_xu_ly: "Đang xử lý",
  cho_review: "Chờ rà soát", hoan_thanh: "Hoàn thành",
};

/** Khối ngữ cảnh gói thầu đang mở — hiện ở khoảng trống giữa sidebar.
 *
 *  Không phải trang trí: trước đây từ trang Kết quả muốn sang Tiêu chí phải quay về gói thầu rồi
 *  bấm tiếp. Ba liên kết này đi thẳng từ bất kỳ trang con nào. */
function PackageContext({ pkg, pathname }: { pkg: PkgBrief; pathname: string }) {
  const base = `/packages/${pkg.id}`;
  const links = [
    { to: base, label: "Tài liệu & nhà thầu" },
    { to: `${base}/rubric`, label: "Tiêu chuẩn đánh giá" },
    { to: `${base}/evaluation`, label: "Kết quả đánh giá" },
  ];
  return (
    <div className="abes-pkg">
      <div className="abes-pkg-label">Gói thầu đang mở</div>
      <div className="abes-pkg-ma mono">{pkg.ma_so}</div>
      <div className="abes-pkg-ten">{pkg.ten}</div>
      <div className="abes-pkg-status">{TRANG_THAI_LABEL[pkg.trang_thai] ?? pkg.trang_thai}</div>
      <div className="abes-pkg-links">
        {links.map((l) => (
          <Link key={l.to} to={l.to}
            className={`abes-pkg-link${pathname === l.to ? " is-active" : ""}`}>
            {l.label}
          </Link>
        ))}
      </div>
    </div>
  );
}

function AiBadge({ health }: { health: HealthData | null }) {
  if (!health) return null;
  const isReal = health.ai_mode === "real";
  return (
    <Tooltip title={isReal ? `Mô hình: ${health.ai_model}` : "Chế độ mô phỏng (mock)"}>
      <div className="abes-ai-badge">
        <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-2)" }}>
          <span
            className="abes-ai-dot"
            style={{ background: isReal ? "#4ADE80" : "rgba(255,255,255,0.35)" }}
          />
          <span style={{
            fontSize: "var(--fs-meta)",
            fontWeight: 600,
            color: isReal ? "rgba(255,255,255,0.9)" : "rgba(255,255,255,0.45)",
            letterSpacing: "0.04em",
            fontFamily: "var(--font-mono)",
          }}>
            {isReal ? health.ai_model : "MOCK"}
          </span>
        </div>
      </div>
    </Tooltip>
  );
}

export default function App() {
  const location = useLocation();
  const [health, setHealth] = useState<HealthData | null>(null);
  const [pkg, setPkg] = useState<PkgBrief | null>(null);

  useEffect(() => {
    api.get("/health").then((r) => {
      if (r.data?.success) setHealth(r.data.data as HealthData);
    }).catch(() => {});
  }, []);

  const pkgId = location.pathname.match(/^\/packages\/(\d+)/)?.[1];
  useEffect(() => {
    if (!pkgId) { setPkg(null); return; }
    api.get(`/packages/${pkgId}`)
      .then((r) => setPkg(unwrap<PkgBrief>(r)))
      .catch(() => setPkg(null));
  }, [pkgId]);
  const pkgName = pkg?.ma_so ?? "";

  const selectedKey = location.pathname.startsWith("/packages") ? "pkg" : "home";

  const crumbs = [{ title: <Link to="/">Tổng quan</Link> }];
  if (location.pathname.startsWith("/packages"))
    crumbs.push({ title: <Link to="/packages">Gói thầu</Link> });
  if (pkgId)
    crumbs.push({ title: <Link to={`/packages/${pkgId}`}>{pkgName || `#${pkgId}`}</Link> });
  if (location.pathname.endsWith("/evaluation")) crumbs.push({ title: <span>Kết quả</span> });
  if (location.pathname.endsWith("/rubric")) crumbs.push({ title: <span>Tiêu chí</span> });

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Layout.Sider width={220} className="abes-sider" style={{ position: "fixed", height: "100vh", left: 0, top: 0, zIndex: 100 }}>
        <div className="abes-logo">
          <div className="abes-logo-mark">ABES</div>
          <div className="abes-logo-sub">Đánh giá hồ sơ dự thầu</div>
        </div>
        <div className="abes-nav">
          <Menu
            mode="inline"
            selectedKeys={[selectedKey]}
            items={[
              {
                key: "home",
                icon: <BarChartOutlined />,
                label: <Link to="/">Tổng quan</Link>,
              },
              {
                key: "pkg",
                icon: <FolderOpenOutlined />,
                label: <Link to="/packages">Gói thầu</Link>,
              },
            ]}
          />
          {pkg && <PackageContext pkg={pkg} pathname={location.pathname} />}
        </div>
        <AiBadge health={health} />
      </Layout.Sider>

      {/* minWidth:0 để cột nội dung co được: là flex item, mặc định min-width:auto khiến nó nở
          theo nội dung rộng nhất (thanh tab nhiều nhà thầu) và đẩy tràn ngang cả trang. */}
      <Layout style={{ marginLeft: 220, minWidth: 0 }}>
        <Layout.Header className="abes-header">
          <Breadcrumb items={crumbs} />
        </Layout.Header>

        <Layout.Content className="abes-content">
          <div className="app-max">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/packages" element={<Packages />} />
              <Route path="/packages/:id" element={<PackageDetail />} />
              <Route path="/packages/:id/evaluation" element={<Evaluation />} />
              <Route path="/packages/:id/rubric" element={<Rubric />} />
            </Routes>
          </div>
        </Layout.Content>
      </Layout>
    </Layout>
  );
}
