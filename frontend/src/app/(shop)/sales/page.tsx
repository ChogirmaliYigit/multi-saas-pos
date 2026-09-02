import type { Metadata } from "next";
import { Receipt } from "lucide-react";

import { ComingSoon } from "@/components/layout/coming-soon";
import { PageHeader } from "@/components/layout/page-header";

export const metadata: Metadata = { title: "Sales" };

export default function SalesPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Sales"
        description="Every completed order, refunds and voids."
      />
      <ComingSoon
        icon={Receipt}
        title="Sales"
        description="This screen is built in Step 5."
      />
    </div>
  );
}
