import { Layout, Menu } from "antd";
import { Link, Route, Routes } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Packages from "./pages/Packages";
import PackageDetail from "./pages/PackageDetail";
import Evaluation from "./pages/Evaluation";
import DeCuong from "./pages/DeCuong";

export default function App() {
  return (
    <Layout className="min-h-screen">
      <Layout.Header>
        <div className="text-white text-lg font-semibold float-left mr-8">ABES</div>
        <Menu theme="dark" mode="horizontal" items={[
          { key: "home", label: <Link to="/">Tổng quan</Link> },
          { key: "pkg", label: <Link to="/packages">Gói thầu</Link> },
        ]} />
      </Layout.Header>
      <Layout.Content className="p-6">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/packages" element={<Packages />} />
          <Route path="/packages/:id" element={<PackageDetail />} />
          <Route path="/packages/:id/evaluation" element={<Evaluation />} />
          <Route path="/packages/:id/de-cuong" element={<DeCuong />} />
        </Routes>
      </Layout.Content>
    </Layout>
  );
}
