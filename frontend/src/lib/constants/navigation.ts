export interface NavItem {
  title: string;
  href: string;
  iconName: string;
  badge?: string;
}

export const MAIN_NAV_ITEMS: NavItem[] = [
  {
    title: "Overview",
    href: "/dashboard",
    iconName: "LayoutDashboard",
  },
  {
    title: "Connection Pools",
    href: "/pools",
    iconName: "Network",
  },
  {
    title: "Boxes",
    href: "/pools/default/boxes",
    iconName: "Box",
  },
  {
    title: "Deployments",
    href: "/deployments",
    iconName: "Rocket",
  },
  {
    title: "Projects",
    href: "/projects/overview",
    iconName: "FolderGit2",
  },
  {
    title: "Settings",
    href: "/settings",
    iconName: "Settings",
  },
];
