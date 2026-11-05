
import { NavLink } from "react-router";

import {
  House,
  ClipboardList,
  Sparkles,
  UserRound,
} from "lucide-react";

// 공통 메뉴를 배열로 관리한다.
// 화면이 추가되더라도 메뉴 정의만 변경하면 된다.
const menuItems = [
  {
    path: "/home",
    label: "홈",
    icon: House,
  },
  {
    path: "/records",
    label: "건강기록",
    icon: ClipboardList,
  },
  {
    path: "/chat",
    label: "FITIF AI",
    icon: Sparkles,
  },
  {
    path: "/profile",
    label: "내 정보",
    icon: UserRound,
  },
];

export default function BottomNavigation() {
  return (
    <nav
      className="bottom-navigation"
      aria-label="주 메뉴"
    >
      {menuItems.map((item) => {
        const Icon = item.icon;

        return (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              `nav-item ${isActive ? "active" : ""}`
            }
          >
            <Icon size={23} strokeWidth={2} />

            <span>{item.label}</span>

            <span className="active-indicator" />
          </NavLink>
        );
      })}
    </nav>
  );
}
