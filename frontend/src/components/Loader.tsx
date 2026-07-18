import { Button, Spin } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import type { ReactNode } from "react";

/**
 * Bọc nội dung phụ thuộc dữ liệu tải bất đồng bộ:
 * - loading -> Spin (không còn màn trắng)
 * - error   -> hộp lỗi + nút thử lại (không nuốt lỗi im lặng)
 */
export default function Loader({ loading, error, onRetry, children }: {
  loading: boolean; error?: string | null; onRetry?: () => void; children: ReactNode;
}) {
  if (loading)
    return (
      <div style={{ textAlign: "center", padding: "80px 0" }}>
        <Spin size="large" />
      </div>
    );
  if (error)
    return (
      <div style={{ textAlign: "center", padding: "60px 0", background: "var(--paper)",
                    border: "1px solid var(--line)", borderRadius: 8 }}>
        <div style={{ color: "var(--fail)", fontSize: "var(--fs-body)", marginBottom: 12 }}>Không tải được dữ liệu: {error}</div>
        {onRetry && <Button icon={<ReloadOutlined />} onClick={onRetry}>Thử lại</Button>}
      </div>
    );
  return <>{children}</>;
}
