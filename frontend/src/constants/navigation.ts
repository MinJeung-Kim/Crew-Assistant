export type NavIconKey =
  | "chat"
  | "overview"
  | "agents"
  | "tools"
  | "env"
  | "settings"
  | "billing"
  | "usage";

export interface NavItemConfig {
  label: string;
  path: string;
  icon: NavIconKey;
  description: string;
}

export interface NavSectionConfig {
  label: string;
  items: NavItemConfig[];
}

export const NAV_SECTIONS: NavSectionConfig[] = [
  {
    label: "Build",
    items: [
      {
        label: "Chat",
        path: "/chat",
        icon: "chat",
        description: "Direct gateway chat session for quick interventions.",
      },
      {
        label: "Overview",
        path: "/overview",
        icon: "overview",
        description: "Check system snapshots, trends, and high-level status.",
      },
    ],
  },
  {
    label: "Agent",
    items: [
      {
        label: "Agents",
        path: "/agents",
        icon: "agents",
        description: "Manage agent personas, prompts, and runtime policies.",
      },
      {
        label: "Tools & Integrations",
        path: "/tools-integrations",
        icon: "tools",
        description: "Configure external tools, APIs, and integration health.",
      },
      {
        label: "Environment Variables",
        path: "/environment-variables",
        icon: "env",
        description: "Review and maintain environment secrets and variables.",
      },
    ],
  },
  {
    label: "Manage",
    items: [
      {
        label: "Settings",
        path: "/settings",
        icon: "settings",
        description: "Tune workspace defaults and operational preferences.",
      },
      {
        label: "Billing",
        path: "/billing",
        icon: "billing",
        description: "Monitor plan usage, invoices, and billing controls.",
      },
      {
        label: "Usage",
        path: "/usage",
        icon: "usage",
        description: "Inspect request volume, latency, and token consumption.",
      },
    ],
  },
];

export const NAV_ITEMS: NavItemConfig[] = NAV_SECTIONS.flatMap(
  (section) => section.items
);
