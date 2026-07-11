import { ClarificationsInbox } from "@/components/clarifications/inbox";
import { getSpawndClient } from "@/lib/server/client";

export const dynamic = "force-dynamic";

export default async function ClarificationsPage() {
  const client = await getSpawndClient();
  const clarifications = await client.clarifications.list();

  return (
    <div className="p-6">
      <ClarificationsInbox initialClarifications={clarifications} />
    </div>
  );
}
