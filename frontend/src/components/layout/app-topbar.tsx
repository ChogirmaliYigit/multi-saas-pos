"use client";

import { ShoppingCart } from "lucide-react";
import Link from "next/link";

import { PermissionGate } from "@/components/auth/permission-gate";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import type { NavSection } from "@/lib/navigation";
import { Permission } from "@/lib/permissions";

import { MobileNav } from "./mobile-nav";
import { NavUser } from "./nav-user";
import { ThemeToggle } from "./theme-toggle";

export function AppTopbar({
  sections,
  showPosLink = true,
}: {
  sections: NavSection[];
  showPosLink?: boolean;
}) {
  return (
    <header className="bg-background/80 sticky top-0 z-30 flex h-14 shrink-0 items-center gap-2 border-b px-3 backdrop-blur-sm sm:px-4">
      <MobileNav sections={sections} />
      <div className="flex-1" />

      {showPosLink && (
        <PermissionGate require={Permission.ORDER_CREATE}>
          <Button asChild size="sm" className="gap-2">
            <Link href="/pos">
              <ShoppingCart className="size-4" />
              <span className="hidden sm:inline">POS terminal</span>
            </Link>
          </Button>
        </PermissionGate>
      )}

      <ThemeToggle />
      <Separator orientation="vertical" className="mx-1 h-6" />
      <NavUser />
    </header>
  );
}
