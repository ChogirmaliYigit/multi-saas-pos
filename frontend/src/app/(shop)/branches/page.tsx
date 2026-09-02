import type { Metadata } from "next";
import { Building2 } from "lucide-react";

import { ComingSoon } from "@/components/layout/coming-soon";
import { PageHeader } from "@/components/layout/page-header";

export const metadata: Metadata = { title: "Branches" };

export default function BranchesPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Branches" description="Shop locations and their stock." />
      <ComingSoon
        icon={Building2}
        title="Branches"
        description="This screen is built in Step 5."
      />
    </div>
  );
}
