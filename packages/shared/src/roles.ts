/** Mirrored from apps/api/app/rbac.py — keep in sync. */
export const ROLES = ["admin", "manager", "member"] as const;
export type Role = (typeof ROLES)[number];

export const PERMISSIONS: Record<Role, readonly string[]> = {
  admin: ["*"],
  manager: [
    "cases:read", "cases:write", "cases:assign",
    "connectors:read", "connectors:write",
    "team:dashboard", "team:manage",
    "effort:read", "effort:write", "effort:read_team",
  ],
  member: [
    "cases:read",
    "connectors:read",
    "dashboard:own", "effort:own",
    "effort:read", "effort:write",
  ],
};

export function hasPermission(role: Role, permission: string): boolean {
  const allowed = PERMISSIONS[role];
  return allowed.includes("*") || allowed.includes(permission);
}
