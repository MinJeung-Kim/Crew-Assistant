import {
  IconChat, IconChart, IconLayers, IconStar, IconNode, IconSettings 
} from "../icons";
import styles from "./Sidebar.module.css";

interface SidebarProps {
  isOpen?: boolean;
}

interface NavItemProps {
  icon: React.ReactNode;
  label: string;
  active?: boolean;
}

function NavItem({ icon, label, active }: NavItemProps) {
  return (
    <button
      className={`${styles.navItem} ${active ? styles.navItemActive : ''}`}
    >
      {icon}{label}
    </button>
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
      <div className={styles.logo}>
        <div className={styles.logoIcon}>🦞</div>
        <div>
          <div className={styles.logoTitle}>OPENCLAW</div>
          <div className={styles.logoSubtitle}>GATEWAY DASHBOARD</div>
        </div>
      </div>
      <div className={styles.navContainer}> 
        <SectionLabel label="Build" />
        <NavItem icon={<IconChat />} label="Chat" active />
        <NavItem icon={<IconChart />} label="Overview" /> 
        <SectionLabel label="Agent" />
        <NavItem icon={<IconStar />} label="Agents" />
        <NavItem icon={<IconStar />} label="Tools & Integrations" />
        <NavItem icon={<IconNode />} label="Environment Variables" />
        <SectionLabel label="Manage" />
        <NavItem icon={<IconSettings />} label="Settings" /> 
        <NavItem icon={<IconLayers />} label="Billing" />
        <NavItem icon={<IconChart />} label="Usage" /> 
      </div>
    </div>
  );
}