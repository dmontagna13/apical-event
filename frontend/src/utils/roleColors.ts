interface RoleColor {
  bg: string;
  text: string;
  border: string;
}

const PALETTE: [RoleColor, ...RoleColor[]] = [
  { bg: "bg-amber-100", text: "text-amber-700", border: "border-amber-200" },
  { bg: "bg-sky-100", text: "text-sky-700", border: "border-sky-200" },
  { bg: "bg-emerald-100", text: "text-emerald-700", border: "border-emerald-200" },
  { bg: "bg-rose-100", text: "text-rose-700", border: "border-rose-200" },
  { bg: "bg-lime-100", text: "text-lime-700", border: "border-lime-200" },
  { bg: "bg-indigo-100", text: "text-indigo-700", border: "border-indigo-200" },
  { bg: "bg-orange-100", text: "text-orange-700", border: "border-orange-200" },
  { bg: "bg-fuchsia-100", text: "text-fuchsia-700", border: "border-fuchsia-200" },
];

export function getRoleColor(roleId: string): RoleColor {
  let hash = 0;
  for (let i = 0; i < roleId.length; i += 1) {
    hash = (hash * 31 + roleId.charCodeAt(i)) % PALETTE.length;
  }
  return PALETTE[hash] ?? PALETTE[0];
}
