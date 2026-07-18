import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { ConfigProvider } from "antd";
import viVN from "antd/locale/vi_VN";
import "antd/dist/reset.css";
import "./index.css";
import App from "./App";

// Màu ngữ nghĩa phải khai ở ĐÂY, nếu không AntD dùng bảng màu mặc định của nó và ta có HAI hệ
// màu song song cho cùng một nghĩa (đo được: "đạt" ra xanh rgb(56,158,13) ở Tag nhưng
// rgb(46,125,84) ở pill). Mắt không học được "xanh = đạt" khi xanh có hai giá trị.
const theme = {
  token: {
    colorPrimary: "#0F6E62",
    colorSuccess: "#2E7D54",
    colorError: "#C0392B",
    colorWarning: "#C77D11",
    colorBgContainer: "#FFFFFF",
    colorBgLayout: "#F7F8F6",
    colorBorder: "#E3E6E1",
    colorText: "#14233A",
    colorTextSecondary: "#4B5D73",
    colorTextTertiary: "#4B5D73",     // chặn rgba(0,0,0,.45) — grey thứ ba ngoài bảng màu
    colorTextDescription: "#4B5D73",
    borderRadius: 6,
    fontSize: 14,                      // bậc "body" của thang chữ
    fontFamily: "'Be Vietnam Pro', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  },
  components: {
    Table: {
      headerBg: "#F7F8F6",
      headerColor: "#4B5D73",
    },
    Card: {
      paddingLG: 20,
      headerFontSize: 18,   // tiêu đề thẻ = bậc "lead", trùng vai trò với tên nhà thầu
    },
    Button: {
      colorPrimary: "#0F6E62",
      colorPrimaryHover: "#1A8C7D",
      colorPrimaryActive: "#0A5249",
    },
    Tag: {
      borderRadiusSM: 4,
    },
  },
};

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider theme={theme} locale={viVN}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ConfigProvider>
  </React.StrictMode>
);
