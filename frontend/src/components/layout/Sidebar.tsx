import {
  IconChat, IconChart, IconLink, IconRadio, IconLayers,
  IconCron, IconStar, IconNode, IconSettings, IconBug, IconLog,
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
        <SectionLabel label="Chat" />
        <NavItem icon={<IconChat />} label="Chat" active />
        <SectionLabel label="Control" />
        <NavItem icon={<IconChart />} label="Overview" />
        <NavItem icon={<IconLink />} label="Channels" />
        <NavItem icon={<IconRadio />} label="Instances" />
        <NavItem icon={<IconLayers />} label="Sessions" />
        <NavItem icon={<IconChart />} label="Usage" />
        <NavItem icon={<IconCron />} label="Cron Jobs" />
        <SectionLabel label="Agent" />
        <NavItem icon={<IconStar />} label="Agents" />
        <NavItem icon={<IconStar />} label="Skills" />
        <NavItem icon={<IconNode />} label="Nodes" />
        <SectionLabel label="Settings" />
        <NavItem icon={<IconSettings />} label="Config" />
        <NavItem icon={<IconBug />} label="Debug" />
        <NavItem icon={<IconLog />} label="Logs" />
      </div>
    </div>
  );
}