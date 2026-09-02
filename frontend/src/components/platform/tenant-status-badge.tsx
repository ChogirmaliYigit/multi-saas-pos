import { Ban, CircleDot, Clock, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { TenantStatus } from "@/lib/api/platform-types";

/**
 * Status wears an icon and a word, never colour alone -- "suspended" and
 * "active" must be distinguishable in greyscale and to a colour-blind reader.
 */
const STATUS = {
  active: { label: "Active", icon: CircleDot, variant: "default" as const },
  trial: { label: "Trial", icon: Clock, variant: "secondary" as const },
  suspended: { label: "Suspended", icon: Ban, variant: "destructive" as const },
  cancelled: { label: "Closed", icon: XCircle, variant: "outline" as const },
};

export function TenantStatusBadge({ status }: { status: TenantStatus }) {
  const config = STATUS[status] ?? STATUS.cancelled;
  return (
    <Badge variant={config.variant} className="gap-1.5">
      <config.icon className="size-3" />
      {config.label}
    </Badge>
  );
}
