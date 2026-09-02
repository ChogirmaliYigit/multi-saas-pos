import type { Metadata } from "next";
import { Settings } from "lucide-react";

import { ComingSoon } from "@/components/layout/coming-soon";
import { PageHeader } from "@/components/layout/page-header";

export const metadata: Metadata = { title: "Settings" };

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Settings"
        description="Shop details, taxes and receipt layout."
      />
      <ComingSoon
        icon={Settings}
        title="Settings"
        description="This screen is built in Step 5."
      />
    </div>
  );
}
