import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { ConfigProvider } from "antd";
import viVN from "antd/locale/vi_VN";
import "antd/dist/reset.css";
import "./index.css";
import App from "./App";

const theme = {
  token: {
    colorPrimary: "#0F6E62",
    colorBgContainer: "#FFFFFF",
    colorBgLayout: "#F7F8F6",
    colorBorder: "#E3E6E1",
    colorText: "#14233A",
    colorTextSecondary: "#4B5D73",
    borderRadius: 6,
    fontFamily: "'Be Vietnam Pro', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  },
  components: {
    Table: {
      headerBg: "#F7F8F6",
      headerColor: "#4B5D73",
    },
    Card: {
      paddingLG: 20,
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
