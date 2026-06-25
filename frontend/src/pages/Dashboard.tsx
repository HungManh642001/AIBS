import { useEffect, useState } from "react";
import { Card, Col, Row, Statistic } from "antd";
import { api, unwrap } from "../api/client";
import type { Package } from "../api/types";

export default function Dashboard() {
  const [pkgs, setPkgs] = useState<Package[]>([]);
  useEffect(() => { api.get("/packages").then((r) => setPkgs(unwrap<Package[]>(r))); }, []);
  const byStatus = (s: string) => pkgs.filter((p) => p.trang_thai === s).length;
  return (
    <Row gutter={16}>
      <Col span={6}><Card><Statistic title="Tổng gói thầu" value={pkgs.length} /></Card></Col>
      <Col span={6}><Card><Statistic title="Đang xử lý" value={byStatus("dang_xu_ly")} /></Card></Col>
      <Col span={6}><Card><Statistic title="Chờ review" value={byStatus("cho_review")} /></Card></Col>
      <Col span={6}><Card><Statistic title="Hoàn thành" value={byStatus("hoan_thanh")} /></Card></Col>
    </Row>
  );
}
