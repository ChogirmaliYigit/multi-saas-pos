import type { Metadata } from "next";
import { User } from "lucide-react";

import { ComingSoon } from "@/components/layout/coming-soon";
import { PageHeader } from "@/components/layout/page-header";

export const metadata: Metadata = { title: "Account" };

export default function AccountPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Account"
        description="Your profile, password and terminal PIN."
      />
      <ComingSoon
        icon={User}
        title="Account"
        description="This screen is built in Step 5."
      />
    </div>
  );
}
