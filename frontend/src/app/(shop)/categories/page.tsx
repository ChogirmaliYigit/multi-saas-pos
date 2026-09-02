import type { Metadata } from "next";
import { Tags } from "lucide-react";

import { ComingSoon } from "@/components/layout/coming-soon";
import { PageHeader } from "@/components/layout/page-header";

export const metadata: Metadata = { title: "Categories" };

export default function CategoriesPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Categories"
        description="Organise the catalog and the POS grid."
      />
      <ComingSoon
        icon={Tags}
        title="Categories"
        description="This screen is built in Step 5."
      />
    </div>
  );
}
