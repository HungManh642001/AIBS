import { useEffect, useState } from "react";
import { Layout, Menu, Tooltip } from "antd";
import { BarChartOutlined, FolderOpenOutlined } from "@ant-design/icons";
import { Link, Route, Routes, useLocation } from "react-router-dom";
import { api } from "./api/client";
import Dashboard from "./pages/Dashboard";
import Packages from "./pages/Packages";
import PackageDetail from "./pages/PackageDetail";
import Evaluation from "./pages/Evaluation";
import Rubric from "./pages/Rubric";

interface HealthData {
  ai_mode: "mock" | "real";
  ai_model: string;
}

function AiBadge({ health }: { health: HealthData | null }) {
  if (!health) return null;
  const isReal = health.ai_mode === "real";
  return (
    <Tooltip title={isReal ? `Mô hình: ${health.ai_model}` : "Chế độ mô phỏng (mock)"}>
      <div className="abes-ai-badge">
        <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
          <span
            className="abes-ai-dot"
            style={{ background: isReal ? "#4ADE80" : "rgba(255,255,255,0.35)" }}
          />
          <span style={{
            fontSize: 11,
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

  useEffect(() => {
    api.get("/health").then((r) => {
      if (r.data?.success) setHealth(r.data.data as HealthData);
    }).catch(() => {});
  }, []);

  const selectedKey = location.pathname.startsWith("/packages") ? "pkg" : "home";

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
        </div>
        <AiBadge health={health} />
      </Layout.Sider>

      <Layout style={{ marginLeft: 220 }}>
        <Layout.Header className="abes-header">
          <span style={{ fontSize: 13, color: "var(--ink-muted)", fontWeight: 500 }}>
            {location.pathname === "/" ? "Tổng quan" : "Gói thầu"}
          </span>
          <span style={{ fontSize: 11, color: "var(--ink-muted)", fontFamily: "var(--font-mono)" }}>
            ABES Demo
          </span>
        </Layout.Header>

        <Layout.Content className="abes-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/packages" element={<Packages />} />
            <Route path="/packages/:id" element={<PackageDetail />} />
            <Route path="/packages/:id/evaluation" element={<Evaluation />} />
            <Route path="/packages/:id/rubric" element={<Rubric />} />
          </Routes>
        </Layout.Content>
      </Layout>
    </Layout>
  );
}
