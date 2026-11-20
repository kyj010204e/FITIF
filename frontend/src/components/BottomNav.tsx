import { NavLink } from "react-router";
import type { CSSProperties } from "react";

import house from "../assets/bottom-nav/house.svg";
import clipboardList from "../assets/bottom-nav/clipboard-list.svg";
import sparkles from "../assets/bottom-nav/sparkles.svg";
import userRound from "../assets/bottom-nav/user-round.svg";
import "./BottomNav.css";

type Props = {
  recordsPath: string;
  aiPath: string;
  profilePath: string;
};

export default function BottomNav({ recordsPath, aiPath, profilePath }: Props) {
  const tabs = [
    { label: "홈", to: "/home", icon: house, end: true },
    { label: "건강기록", to: recordsPath, icon: clipboardList },
    { label: "FITIF AI", to: aiPath, icon: sparkles },
    { label: "내 정보", to: profilePath, icon: userRound },
  ];

  return (
    <nav className="fitif-bottom-nav" aria-label="하단 메뉴">
      {tabs.map(({ label, to, icon, end }) => (
        <NavLink key={label} to={to} end={end} className="fitif-bottom-nav__tab">
          <span
            className="fitif-bottom-nav__icon"
            style={{ "--tab-icon": `url("${icon}")` } as CSSProperties}
            aria-hidden="true"
          />
          <span>{label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
