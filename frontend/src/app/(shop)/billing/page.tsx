import type { Metadata } from "next";
import { CreditCard } from "lucide-react";

import { ComingSoon } from "@/components/layout/coming-soon";
import { PageHeader } from "@/components/layout/page-header";

export const metadata: Metadata = { title: "Billing" };

export default function BillingPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Billing"
        description="Your plan, invoices and usage limits."
      />
      <ComingSoon
        icon={CreditCard}
        title="Billing"
        description="This screen is built in Step 5."
      />
    </div>
  );
}
