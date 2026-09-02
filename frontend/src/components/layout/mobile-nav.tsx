"use client";

import { Menu, Store } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import type { NavSection } from "@/lib/navigation";
import { useAuthStore } from "@/lib/stores/auth-store";
import { cn } from "@/lib/utils";

export function MobileNav({ sections }: { sections: NavSection[] }) {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const permissions = useAuthStore((s) => s.permissions);

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="md:hidden"
          aria-label="Open menu"
        >
          <Menu className="size-5" />
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="w-72 p-0">
        <SheetHeader className="h-14 flex-row items-center gap-2 border-b px-4">
          <div className="bg-primary text-primary-foreground flex size-8 items-center justify-center rounded-lg">
            <Store className="size-4" />
          </div>
          <SheetTitle className="text-base">Shop admin</SheetTitle>
        </SheetHeader>
        <nav className="flex flex-col gap-4 overflow-y-auto p-2">
          {sections.map((section) => {
            const visible = section.items.filter(
              (item) => !item.permission || permissions.has(item.permission),
            );
            if (visible.length === 0) return null;
            return (
              <div key={section.label} className="flex flex-col gap-0.5">
                <p className="text-muted-foreground px-3 py-1 text-xs font-medium tracking-wide uppercase">
                  {section.label}
                </p>
                {visible.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setOpen(false)}
                    className={cn(
                      "flex items-center gap-3 rounded-md px-3 py-2.5 text-sm",
                      pathname.startsWith(item.href)
                        ? "bg-accent text-accent-foreground font-medium"
                        : "text-muted-foreground",
                    )}
                  >
                    <item.icon className="size-4.5" />
                    {item.title}
                  </Link>
                ))}
              </div>
            );
          })}
        </nav>
      </SheetContent>
    </Sheet>
  );
}
