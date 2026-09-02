import { Store } from "lucide-react";
import Link from "next/link";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="flex h-16 items-center px-6">
        <Link href="/" className="flex items-center gap-2 font-semibold">
          <span className="bg-primary text-primary-foreground flex size-8 items-center justify-center rounded-lg">
            <Store className="size-4" />
          </span>
          POS
        </Link>
      </header>
      {/* overflow-y-auto + my-auto: centred when the form fits, scrollable
          when it does not. A rigidly centred flex child clips its overflow,
          which hid the submit button on short laptop viewports. */}
      <main className="flex flex-1 justify-center overflow-y-auto px-4 pb-10">
        <div className="my-auto w-full max-w-md py-4">{children}</div>
      </main>
    </div>
  );
}
