import { redirect } from "next/navigation";

/**
 * The root is a router, not a page. Where a visitor belongs depends on their
 * role, which only the client knows once the session is rebuilt -- so send
 * everyone to /dashboard and let AuthGuard bounce them onward. Marketing site
 * lives on the apex domain, outside this app.
 */
export default function RootPage() {
  redirect("/dashboard");
}
