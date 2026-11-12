import { Outlet } from "react-router";
import fitifIcon from "../assets/fitif-app-icon.png";
import fitifLogo from "../assets/fitif-logo.png";
import "./AppLayout.css";
import BottomNav from "../components/BottomNav";
export default function AppLayout() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-brand-inline">
          <img
            src={fitifIcon}
            alt=""
            className="app-brand-icon"
          />
          <img
            src={fitifLogo}
            alt="FITIF"
            className="app-brand-wordmark"
          />
        </div>
      </header>

      <main>
        <Outlet />
      </main>
      <BottomNav recordsPath="/records" aiPath="/chat" profilePath="/profile" />
    </div>
  );
}
