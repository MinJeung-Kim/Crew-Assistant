import { Fragment, type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import {
  IconChat,
  IconChart,
  IconLayers,
  IconStar,
  IconNode,
  IconSettings,
} from "../icons";
import {
  NAV_SECTIONS,
  type NavIconKey,
} from "../../constants/navigation";
import styles from "./Sidebar.module.css";

interface SidebarProps {
  isOpen?: boolean;
}

interface NavItemProps {
  icon: ReactNode;
  label: string;
  to: string;
}

const ICON_BY_KEY: Record<NavIconKey, ReactNode> = {
  chat: <IconChat />,
  overview: <IconChart />,
  flow: <IconStar />,
  tools: <IconNode />,
  settings: <IconSettings />,
  billing: <IconLayers />,
  usage: <IconChart />,
};

function NavItem({ icon, label, to }: NavItemProps) {
  return (
    <NavLink
      to={to}
      end={to === "/chat"}
      className={({ isActive }) =>
        `${styles.navItem} ${isActive ? styles.navItemActive : ""}`
      }
    >
      {icon}
      <span>{label}</span>
    </NavLink>
  );
}

function SectionLabel({ label }: { label: string }) {
  return (
    <div className={styles.sectionLabel}>
      {label}
    </div>
  );
}

export function Sidebar({ isOpen = true }: SidebarProps) {
  return (
    <div className={`${styles.sidebar} ${!isOpen ? styles.sidebarCollapsed : ''}`}>
      <NavLink to="/chat" className={styles.logo}>
        <div className={styles.logoIcon}>🪄</div>
        <div>
          <div className={styles.logoTitle}>Orchestration</div>
          <div className={styles.logoSubtitle}>GATEWAY DASHBOARD</div>
        </div>
      </NavLink>
      <div className={styles.navContainer}>
        {NAV_SECTIONS.map((section) => (
          <Fragment key={section.label}>
            <SectionLabel label={section.label} />
            {section.items.map((item) => (
              <NavItem
                key={item.path}
                icon={ICON_BY_KEY[item.icon]}
                label={item.label}
                to={item.path}
              />
            ))}
          </Fragment>
        ))}
      </div>
    </div>
  );
}