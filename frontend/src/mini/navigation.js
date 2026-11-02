export const NAV_ITEMS = Object.freeze([
  { id: "today", path: "/today", label: "Today", title: "Today", icon: "sun", group: "everyday" },
  { id: "chat", path: "/chat", label: "Talk", title: "Talk to ORA", icon: "message", group: "everyday" },
  { id: "plan", path: "/plan", label: "Plan", title: "My plan", icon: "check", group: "everyday" },
  { id: "memory", path: "/memory", label: "Memory", title: "Memory", icon: "brain", group: "everyday" },
  { id: "tools", path: "/tools", label: "Tools & activity", title: "Tools & activity", icon: "tool", group: "workspace" },
  { id: "projects", path: "/projects", label: "Projects & desktop", title: "Projects & desktop", icon: "folder", group: "workspace" },
  { id: "connections", path: "/connections", label: "Connections", title: "Connections", icon: "settings", group: "workspace" },
]);

export const CORE_NAV_ITEMS = NAV_ITEMS.filter((item) => item.group === "everyday");
export const MORE_NAV_ITEMS = NAV_ITEMS.filter((item) => item.group === "workspace");
export const NAV_BY_ID = Object.fromEntries(NAV_ITEMS.map((item) => [item.id, item]));
export const NAV_BY_PATH = Object.fromEntries(NAV_ITEMS.map((item) => [item.path, item]));
